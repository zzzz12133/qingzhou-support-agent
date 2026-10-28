package com.lightdesk.support.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.lightdesk.support.api.ApiDtos;
import com.lightdesk.support.config.AppProperties;
import com.lightdesk.support.model.ChatMessage;
import com.lightdesk.support.model.Session;
import com.lightdesk.support.model.SessionSummary;
import com.lightdesk.support.store.SessionStore;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.http.MediaType;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Pattern;

@Service
public class ChatService {

    private static final Logger log = LoggerFactory.getLogger(ChatService.class);
    private static final Pattern USER_ID = Pattern.compile("^[A-Za-z0-9_-]{3,64}$");
    private static final Duration IDEMPOTENCY_TTL = Duration.ofMinutes(10);

    private final SessionStore store;
    private final AgentClient agentClient;
    private final RateLimiter rateLimiter;
    private final AppProperties properties;
    private final ObjectMapper objectMapper;
    private final ThreadPoolTaskExecutor executor;

    private final Map<String, String> activeBySession = new ConcurrentHashMap<>();
    private final Map<String, ChatRun> runs = new ConcurrentHashMap<>();
    private final Map<String, AtomicInteger> concurrentByUser = new ConcurrentHashMap<>();
    private final Map<String, Long> seenClientMessages = new ConcurrentHashMap<>();

    public ChatService(
            SessionStore store,
            AgentClient agentClient,
            RateLimiter rateLimiter,
            AppProperties properties,
            ObjectMapper objectMapper,
            @Qualifier("chatExecutor") ThreadPoolTaskExecutor executor
    ) {
        this.store = store;
        this.agentClient = agentClient;
        this.rateLimiter = rateLimiter;
        this.properties = properties;
        this.objectMapper = objectMapper;
        this.executor = executor;
    }

    public SseEmitter start(ApiDtos.ChatRequest request) {
        validateUserId(request.userId());
        String message = request.message() == null ? "" : request.message().trim();
        if (message.isEmpty()) {
            throw ApiException.badRequest("消息不能为空");
        }
        if (message.length() > properties.getMaxMessageLength()) {
            throw ApiException.badRequest("消息不能超过 " + properties.getMaxMessageLength() + " 字");
        }
        if (request.clientMessageId() == null || request.clientMessageId().isBlank()) {
            throw ApiException.badRequest("缺少客户端消息 ID");
        }

        cleanupIdempotency();
        String idempotencyKey = request.userId() + ":" + request.clientMessageId();
        long now = System.currentTimeMillis();
        Long previous = seenClientMessages.get(idempotencyKey);
        if (previous != null && now - previous < IDEMPOTENCY_TTL.toMillis()) {
            throw ApiException.conflict("DUPLICATE_REQUEST", "这条消息已经提交过了，请勿重复发送。");
        }
        seenClientMessages.put(idempotencyKey, now);

        RateLimiter.Decision decision = rateLimiter.allow(request.userId());
        if (!decision.allowed()) {
            seenClientMessages.remove(idempotencyKey);
            throw ApiException.tooMany(decision.retryAfterSeconds());
        }
        if (!acquireUserSlot(request.userId())) {
            seenClientMessages.remove(idempotencyKey);
            throw ApiException.conflict("USER_BUSY", "当前还有对话在处理中，请稍后再试。");
        }

        Session session;
        String messageId = UUID.randomUUID().toString();
        ChatRun run = null;
        String sessionIdForCleanup = null;
        try {
            if (request.conversationId() == null || request.conversationId().isBlank()) {
                session = store.create(request.userId(), null);
            } else {
                session = store.get(request.conversationId(), request.userId());
                if (session == null) {
                    throw ApiException.notFound("会话不存在或已被删除");
                }
            }
            sessionIdForCleanup = session.getId();
            String active = activeBySession.putIfAbsent(session.getId(), messageId);
            if (active != null) {
                throw ApiException.conflict("SESSION_BUSY", "上一条消息还在生成，请先等待或点停止。");
            }

            ChatMessage userMessage = store.appendUser(session, message);
            SseEmitter emitter = new SseEmitter(properties.getSseTimeoutMs());
            run = new ChatRun(messageId, session.getId(), request.userId(), request.clientMessageId(), emitter);
            runs.put(messageId, run);

            ChatRun finalRun = run;
            String finalSessionId = session.getId();
            emitter.onCompletion(() -> handleDisconnect(finalRun));
            emitter.onTimeout(() -> {
                log.info("SSE 超时 session={} message={}", finalSessionId, finalRun.getMessageId());
                cancelInternal(finalRun, true);
            });
            emitter.onError(error -> {
                log.info("SSE 连接异常 session={}: {}", finalSessionId, error.getMessage());
                cancelInternal(finalRun, true);
            });

            Map<String, Object> meta = new LinkedHashMap<>();
            meta.put("type", "meta");
            meta.put("conversationId", session.getId());
            meta.put("sessionId", session.getId());
            meta.put("messageId", messageId);
            meta.put("userMessage", userMessage);
            meta.put("provider", "Agent");
            meta.put("createdAt", Instant.now().toString());
            send(run, objectMapper.writeValueAsString(meta));

            ChatRun taskRun = run;
            Session taskSession = session;
            executor.execute(() -> streamRun(taskRun, taskSession));
            return emitter;
        } catch (RuntimeException | IOException e) {
            if (run != null) {
                runs.remove(run.getMessageId());
                run.markFinished();
            }
            if (sessionIdForCleanup != null) {
                activeBySession.remove(sessionIdForCleanup, messageId);
            }
            seenClientMessages.remove(idempotencyKey);
            releaseUserSlot(request.userId());
            if (e instanceof ApiException api) {
                throw api;
            }
            if (e instanceof TaskRejectedException) {
                throw new ApiException(
                        org.springframework.http.HttpStatus.SERVICE_UNAVAILABLE,
                        "QUEUE_FULL",
                        "当前排队人数较多，请稍后重试。",
                        3,
                        true
                );
            }
            throw new IllegalStateException("启动对话失败", e);
        }
    }

    public boolean cancel(String messageId, String userId) {
        ChatRun run = runs.get(messageId);
        if (run == null) {
            return false;
        }
        if (!run.getUserId().equals(userId)) {
            throw ApiException.forbidden("无权停止该对话");
        }
        return cancelInternal(run, false);
    }

    private boolean cancelInternal(ChatRun run, boolean completeEmitter) {
        if (!run.beginCancel()) {
            return false;
        }
        // 先同步通知 Agent 取消任务，再关闭本地流；避免断连先清空 Python 的运行注册表。
        agentClient.cancel(run.getSessionId(), run.getClientMessageId());
        run.cancel();
        if (completeEmitter) {
            try {
                run.getEmitter().complete();
            } catch (Exception ignored) {
                // 连接可能已经被容器关闭。
            }
        }
        return true;
    }

    private void handleDisconnect(ChatRun run) {
        if (run.isFinished()) {
            return;
        }
        log.info("客户端断开 session={} message={}", run.getSessionId(), run.getMessageId());
        cancelInternal(run, false);
    }

    private void streamRun(ChatRun run, Session session) {
        boolean persisted = false;
        boolean errorSent = false;
        InputStream input = null;
        try {
            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("sessionId", run.getSessionId());
            payload.put("userId", run.getUserId());
            payload.put("message", lastUserContent(session));
            payload.put("clientMessageId", run.getClientMessageId());
            payload.put("channel", "web");

            HttpResponse<InputStream> response = agentClient.openStream(payload);
            input = response.body();
            run.attachUpstream(input);

            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(input, StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    if (run.isCancelled()) {
                        break;
                    }
                    if (line.isBlank()) {
                        continue;
                    }
                    JsonNode node;
                    try {
                        node = objectMapper.readTree(line);
                    } catch (IOException parseError) {
                        log.warn("Agent 返回了无法解析的行，已跳过: {}", line.substring(0, Math.min(120, line.length())));
                        continue;
                    }
                    String type = node.path("type").asText("");
                    // 后端已经发过 meta，忽略上游的重复 meta。
                    if ("meta".equals(type)) {
                        continue;
                    }
                    if ("token".equals(type)) {
                        run.appendAnswer(node.path("text").asText(""));
                    }
                    if ("done".equals(type)) {
                        persisted = persistDone(run, session, node);
                        ObjectNode done = (ObjectNode) node;
                        ChatMessage stored = session.getMessages().stream()
                                .filter(item -> run.getMessageId().equals(item.getId()))
                                .reduce((first, second) -> second)
                                .orElse(null);
                        if (stored != null) {
                            done.set("message", objectMapper.valueToTree(stored));
                        }
                        done.put("conversationId", session.getId());
                        done.put("sessionTitle", session.getTitle());
                        send(run, objectMapper.writeValueAsString(done));
                        return;
                    }
                    if ("error".equals(type)) {
                        errorSent = true;
                    }
                    if (!send(run, line)) {
                        return;
                    }
                    if ("error".equals(type)) {
                        return;
                    }
                }
            }

            if (!run.isCancelled() && !errorSent) {
                sendError(run, "STREAM_INTERRUPTED", "回答生成中断了，请重试。", true);
            }
        } catch (AgentClient.AgentUnavailableException e) {
            log.error("Agent 服务不可用: {}", e.getMessage());
            sendError(run, "AGENT_UNAVAILABLE", "Agent 服务暂时不可用，请确认 Python 服务已启动。", true);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            log.info("Agent 流读取被中断 message={}", run.getMessageId());
        } catch (IOException e) {
            if (!run.isCancelled()) {
                log.warn("读取 Agent 流失败 message={}: {}", run.getMessageId(), e.getMessage());
                sendError(run, "AGENT_STREAM_ERROR", "与 Agent 的连接中断，请重试。", true);
            }
        } catch (Exception e) {
            log.error("对话处理异常 message={}", run.getMessageId(), e);
            if (!run.isCancelled()) {
                sendError(run, "INTERNAL_ERROR", "服务处理异常，请稍后重试。", true);
            }
        } finally {
            if (!persisted) {
                persistPartial(run, session);
            }
            if (input != null) {
                try {
                    input.close();
                } catch (IOException ignored) {
                    // 已结束时关闭失败无影响。
                }
            }
            cleanup(run);
        }
    }

    private boolean persistDone(ChatRun run, Session session, JsonNode node) {
        try {
            String content = node.path("content").asText(run.partialAnswer());
            Map<String, Object> metadata = new LinkedHashMap<>();
            metadata.put("provider", node.path("provider").asText("Agent"));
            metadata.put("citations", objectMapper.convertValue(node.path("citations"), List.class));
            metadata.put("usage", objectMapper.convertValue(node.path("usage"), Map.class));
            metadata.put("grounding", objectMapper.convertValue(node.path("grounding"), Map.class));
            metadata.put("trace", objectMapper.convertValue(node.path("trace"), List.class));
            metadata.put("intent", node.path("intent").asText(""));
            metadata.put("intentLabel", node.path("intentLabel").asText(""));
            metadata.put("cacheHit", node.path("cacheHit").asBoolean(false));
            metadata.put("degraded", node.path("degraded").asBoolean(false));
            metadata.put("durationMs", node.path("durationMs").asLong(0));
            store.appendAssistant(session, run.getMessageId(), content, "done", metadata);
            return true;
        } catch (Exception e) {
            log.error("保存助手消息失败 message={}", run.getMessageId(), e);
            return false;
        }
    }

    private void persistPartial(ChatRun run, Session session) {
        String partial = run.partialAnswer();
        if (partial == null || partial.isBlank()) {
            return;
        }
        try {
            Map<String, Object> metadata = new LinkedHashMap<>();
            metadata.put("provider", "生成中断");
            metadata.put("citations", List.of());
            metadata.put("stopped", true);
            store.appendAssistant(
                    session,
                    run.getMessageId(),
                    partial,
                    run.isCancelled() ? "stopped" : "partial",
                    metadata
            );
        } catch (Exception e) {
            log.warn("保存中断消息失败 message={}: {}", run.getMessageId(), e.getMessage());
        }
    }

    private void cleanup(ChatRun run) {
        if (!run.isFinished()) {
            run.markFinished();
        }
        run.closeUpstream();
        runs.remove(run.getMessageId(), run);
        activeBySession.remove(run.getSessionId(), run.getMessageId());
        releaseUserSlot(run.getUserId());
        try {
            run.getEmitter().complete();
        } catch (Exception ignored) {
            // 已完成或断开。
        }
    }

    private boolean send(ChatRun run, String json) {
        if (run.isCancelled()) {
            return false;
        }
        try {
            run.getEmitter().send(SseEmitter.event().data(json, MediaType.APPLICATION_JSON));
            return true;
        } catch (Exception e) {
            log.debug("SSE 发送失败 message={}: {}", run.getMessageId(), e.getMessage());
            cancelInternal(run, false);
            return false;
        }
    }

    private void sendError(ChatRun run, String code, String message, boolean retryable) {
        if (run.isCancelled()) {
            return;
        }
        try {
            String json = objectMapper.writeValueAsString(Map.of(
                    "type", "error",
                    "code", code,
                    "message", message,
                    "retryable", retryable
            ));
            send(run, json);
        } catch (Exception e) {
            log.debug("发送错误事件失败 message={}: {}", run.getMessageId(), e.getMessage());
        }
    }

    public Session createSession(String userId, String title) {
        validateUserId(userId);
        return store.create(userId, title);
    }

    public List<SessionSummary> listSessions(String userId) {
        validateUserId(userId);
        return store.list(userId);
    }

    public Session getSession(String sessionId, String userId) {
        validateUserId(userId);
        Session session = store.get(sessionId, userId);
        if (session == null) {
            throw ApiException.notFound("会话不存在或已被删除");
        }
        return session;
    }

    public void deleteSession(String sessionId, String userId) {
        validateUserId(userId);
        if (activeBySession.containsKey(sessionId)) {
            throw ApiException.conflict("SESSION_BUSY", "会话正在生成回答，暂不能删除。");
        }
        store.delete(sessionId, userId);
    }

    public Map<String, Object> sessionMemory(String sessionId, String userId) {
        validateUserId(userId);
        Session session = store.get(sessionId, userId);
        if (session == null) {
            throw ApiException.notFound("会话不存在或已被删除");
        }
        return agentClient.sessionMemory(sessionId, userId);
    }

    public boolean isActive(String sessionId) {
        return activeBySession.containsKey(sessionId);
    }

    public RateLimiter.Decision rateLimit(String userId) {
        return rateLimiter.allow(userId);
    }

    private void validateUserId(String userId) {
        if (userId == null || !USER_ID.matcher(userId).matches()) {
            throw ApiException.badRequest("用户 ID 不合法");
        }
    }

    private boolean acquireUserSlot(String userId) {
        AtomicInteger counter = concurrentByUser.computeIfAbsent(userId, key -> new AtomicInteger());
        while (true) {
            int current = counter.get();
            if (current >= properties.getMaxConcurrentPerUser()) {
                return false;
            }
            if (counter.compareAndSet(current, current + 1)) {
                return true;
            }
        }
    }

    private void releaseUserSlot(String userId) {
        AtomicInteger counter = concurrentByUser.get(userId);
        if (counter == null) {
            return;
        }
        int remaining = counter.decrementAndGet();
        if (remaining <= 0) {
            concurrentByUser.remove(userId, counter);
        }
    }

    private void cleanupIdempotency() {
        if (seenClientMessages.size() < 400) {
            return;
        }
        long cutoff = System.currentTimeMillis() - IDEMPOTENCY_TTL.toMillis();
        seenClientMessages.entrySet().removeIf(entry -> entry.getValue() < cutoff);
    }

    private static String lastUserContent(Session session) {
        for (int index = session.getMessages().size() - 1; index >= 0; index--) {
            ChatMessage message = session.getMessages().get(index);
            if ("user".equals(message.getRole())) {
                return message.getContent();
            }
        }
        return "";
    }

    public Map<String, Object> health() {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("status", "ok");
        data.put("time", Instant.now().toString());
        data.put("sessions", store.stats());
        data.put("activeRuns", runs.size());
        data.put("agent", agentClient.health());
        data.put("limits", Map.of(
                "rateLimitPerMinute", properties.getRateLimitPerMinute(),
                "maxConcurrentPerUser", properties.getMaxConcurrentPerUser(),
                "maxMessageLength", properties.getMaxMessageLength()
        ));
        return data;
    }

    public Map<String, Object> runtime() {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("activeRuns", runs.size());
        data.put("activeSessions", activeBySession.keySet());
        data.put("agentBaseUrl", agentClient.getBaseUrl());
        return data;
    }
}
