package com.lightdesk.support.model;

public record SessionSummary(
        String id,
        String title,
        String updatedAt,
        int messageCount,
        String preview
) {
}
