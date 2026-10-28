package com.lightdesk.support.model;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

public class ChatMessage {

    private String id;
    private String role;
    private String content;
    private String createdAt;
    private String status;
    private Map<String, Object> metadata = new LinkedHashMap<>();

    public ChatMessage() {
    }

    public ChatMessage(String id, String role, String content, String status, Map<String, Object> metadata) {
        this.id = id;
        this.role = role;
        this.content = content;
        this.createdAt = Instant.now().toString();
        this.status = status;
        this.metadata = metadata == null ? new LinkedHashMap<>() : metadata;
    }

    public static ChatMessage user(String content) {
        return new ChatMessage(
                java.util.UUID.randomUUID().toString(),
                "user",
                content,
                "done",
                new LinkedHashMap<>()
        );
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getRole() {
        return role;
    }

    public void setRole(String role) {
        this.role = role;
    }

    public String getContent() {
        return content;
    }

    public void setContent(String content) {
        this.content = content;
    }

    public String getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(String createdAt) {
        this.createdAt = createdAt;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public Map<String, Object> getMetadata() {
        return metadata;
    }

    public void setMetadata(Map<String, Object> metadata) {
        this.metadata = metadata == null ? new LinkedHashMap<>() : metadata;
    }
}
