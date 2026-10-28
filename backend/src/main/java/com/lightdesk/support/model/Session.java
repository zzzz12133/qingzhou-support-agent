package com.lightdesk.support.model;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

public class Session {

    private String id;
    private String userId;
    private String title;
    private String createdAt;
    private String updatedAt;
    private List<ChatMessage> messages = new ArrayList<>();

    public Session() {
    }

    public Session(String id, String userId) {
        this.id = id;
        this.userId = userId;
        this.title = "新对话";
        this.createdAt = Instant.now().toString();
        this.updatedAt = this.createdAt;
        this.messages = new ArrayList<>();
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getUserId() {
        return userId;
    }

    public void setUserId(String userId) {
        this.userId = userId;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(String createdAt) {
        this.createdAt = createdAt;
    }

    public String getUpdatedAt() {
        return updatedAt;
    }

    public void setUpdatedAt(String updatedAt) {
        this.updatedAt = updatedAt;
    }

    public List<ChatMessage> getMessages() {
        return messages;
    }

    public void setMessages(List<ChatMessage> messages) {
        this.messages = messages == null ? new ArrayList<>() : messages;
    }
}
