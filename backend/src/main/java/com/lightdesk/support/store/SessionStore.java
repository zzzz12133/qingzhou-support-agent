package com.lightdesk.support.store;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.lightdesk.support.config.AppProperties;
import com.lightdesk.support.model.ChatMessage;
import com.lightdesk.support.model.Session;
import com.lightdesk.support.model.SessionSummary;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Repository;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Pattern;

@Repository
public class SessionStore {

    private static final Logger log = LoggerFactory.getLogger(SessionStore.class);
    private static final Pattern SESSION_ID = Pattern.compile("^[A-Za-z0-9_-]{6,64}$");

    private final ObjectMapper objectMapper;
    private final Path directory;

    public SessionStore(ObjectMapper objectMapper, AppProperties properties) {
        this.objectMapper = objectMapper;
        this.directory = Path.of(properties.getDataDir()).toAbsolutePath().normalize().resolve("sessions");
        try {
            Files.createDirectories(directory);
        } catch (IOException e) {
            throw new IllegalStateException("无法创建会话目录: " + directory, e);
        }
    }

    public synchronized Session create(String userId, String title) {
        String id = UUID.randomUUID().toString();
        Session session = new Session(id, userId);
        if (title != null && !title.isBlank()) {
            session.setTitle(trimTitle(title));
        }
        save(session);
        return session;
    }

    public synchronized Session get(String id, String userId) {
        Session session = read(id);
        if (session == null) {
            return null;
        }
        if (!session.getUserId().equals(userId)) {
            throw new SecurityException("无权访问该会话");
        }
        return session;
    }

    public synchronized Session getOrThrow(String id, String userId) {
        Session session = get(id, userId);
        if (session == null) {
            throw new IllegalArgumentException("会话不存在");
        }
        return session;
    }

    public synchronized ChatMessage appendUser(Session session, String content) {
        ChatMessage message = ChatMessage.user(content);
        session.getMessages().add(message);
        if ("新对话".equals(session.getTitle())) {
            session.setTitle(trimTitle(content));
        }
        touch(session);
        save(session);
        return message;
    }

    public synchronized ChatMessage appendAssistant(
            Session session,
            String messageId,
            String content,
            String status,
            Map<String, Object> metadata
    ) {
        ChatMessage message = new ChatMessage(messageId, "assistant", content, status, metadata);
        session.getMessages().add(message);
        touch(session);
        save(session);
        return message;
    }

    public synchronized List<SessionSummary> list(String userId) {
        List<SessionSummary> result = new ArrayList<>();
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(directory, "*.json")) {
            for (Path path : stream) {
                try {
                    Session session = objectMapper.readValue(path.toFile(), Session.class);
                    if (!userId.equals(session.getUserId())) {
                        continue;
                    }
                    String preview = session.getMessages().stream()
                            .filter(item -> "assistant".equals(item.getRole()))
                            .reduce((first, second) -> second)
                            .map(ChatMessage::getContent)
                            .map(text -> text.replace('\n', ' '))
                            .map(text -> truncate(text, 54))
                            .orElse("还没有消息");
                    result.add(new SessionSummary(
                            session.getId(),
                            session.getTitle(),
                            session.getUpdatedAt(),
                            session.getMessages().size(),
                            preview
                    ));
                } catch (IOException e) {
                    log.warn("跳过损坏的会话文件 {}: {}", path.getFileName(), e.getMessage());
                }
            }
        } catch (IOException e) {
            log.error("读取会话列表失败", e);
        }
        result.sort(Comparator.comparing(SessionSummary::updatedAt).reversed());
        return result;
    }

    public synchronized void delete(String id, String userId) {
        Session session = get(id, userId);
        if (session == null) {
            return;
        }
        try {
            Files.deleteIfExists(pathFor(id));
        } catch (IOException e) {
            throw new IllegalStateException("删除会话失败", e);
        }
    }

    public synchronized boolean exists(String id, String userId) {
        return get(id, userId) != null;
    }

    private Session read(String id) {
        Path path = pathFor(id);
        if (!Files.exists(path)) {
            return null;
        }
        try {
            return objectMapper.readValue(path.toFile(), Session.class);
        } catch (IOException e) {
            log.error("读取会话 {} 失败", id, e);
            throw new IllegalStateException("会话数据损坏", e);
        }
    }

    private void save(Session session) {
        Path path = pathFor(session.getId());
        Path tmp = path.resolveSibling(path.getFileName() + ".tmp");
        try {
            objectMapper.writerWithDefaultPrettyPrinter().writeValue(tmp.toFile(), session);
            try {
                Files.move(tmp, path, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
            } catch (AtomicMoveNotSupportedException e) {
                Files.move(tmp, path, StandardCopyOption.REPLACE_EXISTING);
            }
        } catch (IOException e) {
            throw new IllegalStateException("保存会话失败", e);
        }
    }

    private Path pathFor(String id) {
        if (id == null || !SESSION_ID.matcher(id).matches()) {
            throw new IllegalArgumentException("非法会话 ID");
        }
        return directory.resolve(id + ".json");
    }

    private static void touch(Session session) {
        session.setUpdatedAt(Instant.now().toString());
    }

    private static String trimTitle(String text) {
        String clean = text == null ? "新对话" : text.replaceAll("\\s+", " ").trim();
        if (clean.isEmpty()) {
            return "新对话";
        }
        return truncate(clean, 24);
    }

    private static String truncate(String text, int max) {
        if (text == null) {
            return "";
        }
        return text.length() <= max ? text : text.substring(0, max - 1).stripTrailing() + "…";
    }

    public Map<String, Object> stats() {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("directory", directory.toString());
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(directory, "*.json")) {
            int count = 0;
            for (Path ignored : stream) {
                count++;
            }
            data.put("sessions", count);
        } catch (IOException e) {
            data.put("sessions", -1);
        }
        return data;
    }
}
