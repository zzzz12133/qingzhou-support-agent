package com.lightdesk.support.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.lightdesk.support.config.AppProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;

@Component
public class AgentClient {

    private static final Logger log = LoggerFactory.getLogger(AgentClient.class);

    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;
    private final String baseUrl;
    private final Duration readTimeout;

    public AgentClient(ObjectMapper objectMapper, AppProperties properties) {
        this.objectMapper = objectMapper;
        this.baseUrl = properties.getAgentBaseUrl().replaceAll("/+$", "");
        this.readTimeout = Duration.ofSeconds(Math.max(10, properties.getAgentReadTimeoutSeconds()));
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(Math.max(1, properties.getAgentConnectTimeoutSeconds())))
                .followRedirects(HttpClient.Redirect.NORMAL)
                .version(HttpClient.Version.HTTP_1_1)
                .build();
    }

    public HttpResponse<InputStream> openStream(Map<String, Object> payload) throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + "/v1/agent/stream"))
                .timeout(readTimeout)
                .header("Content-Type", "application/json; charset=utf-8")
                .header("Accept", "application/x-ndjson")
                .POST(HttpRequest.BodyPublishers.ofString(
                        objectMapper.writeValueAsString(payload),
                        StandardCharsets.UTF_8
                ))
                .build();
        HttpResponse<InputStream> response = httpClient.send(request, HttpResponse.BodyHandlers.ofInputStream());
        if (response.statusCode() != 200) {
            String body;
            try (InputStream input = response.body()) {
                body = new String(input.readNBytes(800), StandardCharsets.UTF_8);
            }
            throw new AgentUnavailableException(
                    "Agent 服务返回 HTTP " + response.statusCode() + ": " + body
            );
        }
        return response;
    }

    /**
     * 同步通知 Python 取消，确保先于关闭上游流到达，避免“断连先清空注册表”的竞态。
     * 超时上限 2 秒，避免停止按钮被下游故障拖住。
     */
    public boolean cancel(String sessionId, String clientMessageId) {
        try {
            String body = objectMapper.writeValueAsString(Map.of(
                    "sessionId", sessionId,
                    "clientMessageId", clientMessageId
            ));
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + "/v1/agent/cancel"))
                    .timeout(Duration.ofSeconds(2))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8))
                    .build();
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            log.info("Agent cancel session={} clientMessage={} http={} body={}",
                    sessionId, clientMessageId, response.statusCode(), response.body());
            return response.statusCode() == 200;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            log.warn("取消 Agent 请求被中断 session={}", sessionId);
            return false;
        } catch (Exception e) {
            log.warn("发送取消请求失败 session={}: {}", sessionId, e.getMessage());
            return false;
        }
    }

    public Map<String, Object> health() {
        Map<String, Object> result = new LinkedHashMap<>();
        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + "/v1/health"))
                    .timeout(Duration.ofSeconds(2))
                    .GET()
                    .build();
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            result.put("status", response.statusCode() == 200 ? "up" : "degraded");
            result.put("httpStatus", response.statusCode());
            if (response.statusCode() == 200) {
                Map<String, Object> body = objectMapper.readValue(
                        response.body(),
                        new TypeReference<Map<String, Object>>() {
                        }
                );
                result.put("providers", body.get("providers"));
                result.put("knowledge", body.get("knowledge"));
                result.put("cache", body.get("cache"));
                result.put("sessions", body.get("sessions"));
                result.put("metrics", body.get("metrics"));
            }
        } catch (Exception e) {
            result.put("status", "down");
            result.put("error", e.getClass().getSimpleName());
        }
        return result;
    }

    public Map<String, Object> sessionMemory(String sessionId, String userId) {
        try {
            String encodedSession = java.net.URLEncoder.encode(sessionId, StandardCharsets.UTF_8);
            String encodedUser = java.net.URLEncoder.encode(userId, StandardCharsets.UTF_8);
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + "/v1/sessions/" + encodedSession + "?user_id=" + encodedUser))
                    .timeout(Duration.ofSeconds(3))
                    .GET()
                    .build();
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() == 200) {
                return objectMapper.readValue(
                        response.body(),
                        new TypeReference<Map<String, Object>>() {
                        }
                );
            }
            return Map.of("available", false, "reason", "HTTP " + response.statusCode());
        } catch (Exception e) {
            return Map.of("available", false, "reason", e.getClass().getSimpleName());
        }
    }

    public String getBaseUrl() {
        return baseUrl;
    }

    public static class AgentUnavailableException extends RuntimeException {
        public AgentUnavailableException(String message) {
            super(message);
        }
    }
}
