package com.lightdesk.support.api;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public final class ApiDtos {

    private ApiDtos() {
    }

    public record ChatRequest(
            @Size(max = 64) String conversationId,
            @NotBlank @Size(max = 64) String userId,
            @NotBlank @Size(max = 4000) String message,
            @NotBlank @Size(max = 80) String clientMessageId
    ) {
    }

    public record CreateSessionRequest(
            @NotBlank @Size(max = 64) String userId,
            @Size(max = 64) String title
    ) {
    }

    public record CancelRequest(
            @NotBlank @Size(max = 64) String userId
    ) {
    }

    public record CancelResponse(boolean cancelled, String message) {
    }

    public record ApiError(
            String code,
            String message,
            Integer retryAfter,
            boolean retryable
    ) {
    }
}
