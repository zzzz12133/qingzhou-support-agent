package com.lightdesk.support.service;

import org.springframework.http.HttpStatus;

public class ApiException extends RuntimeException {

    private final HttpStatus status;
    private final String code;
    private final Integer retryAfter;
    private final boolean retryable;

    public ApiException(HttpStatus status, String code, String message, Integer retryAfter, boolean retryable) {
        super(message);
        this.status = status;
        this.code = code;
        this.retryAfter = retryAfter;
        this.retryable = retryable;
    }

    public static ApiException badRequest(String message) {
        return new ApiException(HttpStatus.BAD_REQUEST, "BAD_REQUEST", message, null, false);
    }

    public static ApiException forbidden(String message) {
        return new ApiException(HttpStatus.FORBIDDEN, "FORBIDDEN", message, null, false);
    }

    public static ApiException notFound(String message) {
        return new ApiException(HttpStatus.NOT_FOUND, "NOT_FOUND", message, null, false);
    }

    public static ApiException conflict(String code, String message) {
        return new ApiException(HttpStatus.CONFLICT, code, message, null, false);
    }

    public static ApiException tooMany(int retryAfter) {
        return new ApiException(
                HttpStatus.TOO_MANY_REQUESTS,
                "RATE_LIMITED",
                "发送太快了，请 " + retryAfter + " 秒后再试。",
                retryAfter,
                true
        );
    }

    public HttpStatus getStatus() {
        return status;
    }

    public String getCode() {
        return code;
    }

    public Integer getRetryAfter() {
        return retryAfter;
    }

    public boolean isRetryable() {
        return retryable;
    }
}
