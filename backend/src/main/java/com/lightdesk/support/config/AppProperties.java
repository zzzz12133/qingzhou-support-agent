package com.lightdesk.support.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public class AppProperties {

    private String agentBaseUrl = "http://127.0.0.1:8001";
    private String dataDir = "./.data";
    private int rateLimitPerMinute = 20;
    private int maxConcurrentPerUser = 2;
    private int maxMessageLength = 2000;
    private long sseTimeoutMs = 120_000;
    private int agentConnectTimeoutSeconds = 5;
    private int agentReadTimeoutSeconds = 90;

    public String getAgentBaseUrl() {
        return agentBaseUrl;
    }

    public void setAgentBaseUrl(String agentBaseUrl) {
        this.agentBaseUrl = agentBaseUrl;
    }

    public String getDataDir() {
        return dataDir;
    }

    public void setDataDir(String dataDir) {
        this.dataDir = dataDir;
    }

    public int getRateLimitPerMinute() {
        return rateLimitPerMinute;
    }

    public void setRateLimitPerMinute(int rateLimitPerMinute) {
        this.rateLimitPerMinute = rateLimitPerMinute;
    }

    public int getMaxConcurrentPerUser() {
        return maxConcurrentPerUser;
    }

    public void setMaxConcurrentPerUser(int maxConcurrentPerUser) {
        this.maxConcurrentPerUser = maxConcurrentPerUser;
    }

    public int getMaxMessageLength() {
        return maxMessageLength;
    }

    public void setMaxMessageLength(int maxMessageLength) {
        this.maxMessageLength = maxMessageLength;
    }

    public long getSseTimeoutMs() {
        return sseTimeoutMs;
    }

    public void setSseTimeoutMs(long sseTimeoutMs) {
        this.sseTimeoutMs = sseTimeoutMs;
    }

    public int getAgentConnectTimeoutSeconds() {
        return agentConnectTimeoutSeconds;
    }

    public void setAgentConnectTimeoutSeconds(int agentConnectTimeoutSeconds) {
        this.agentConnectTimeoutSeconds = agentConnectTimeoutSeconds;
    }

    public int getAgentReadTimeoutSeconds() {
        return agentReadTimeoutSeconds;
    }

    public void setAgentReadTimeoutSeconds(int agentReadTimeoutSeconds) {
        this.agentReadTimeoutSeconds = agentReadTimeoutSeconds;
    }
}
