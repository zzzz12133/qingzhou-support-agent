package com.lightdesk.support.service;

import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.io.InputStream;
import java.util.concurrent.atomic.AtomicBoolean;

public class ChatRun {

    private final String messageId;
    private final String sessionId;
    private final String userId;
    private final String clientMessageId;
    private final SseEmitter emitter;
    private final StringBuilder answer = new StringBuilder();
    private final AtomicBoolean cancelled = new AtomicBoolean(false);
    private final AtomicBoolean cancelNotified = new AtomicBoolean(false);
    private final AtomicBoolean finished = new AtomicBoolean(false);
    private volatile InputStream upstream;

    public ChatRun(
            String messageId,
            String sessionId,
            String userId,
            String clientMessageId,
            SseEmitter emitter
    ) {
        this.messageId = messageId;
        this.sessionId = sessionId;
        this.userId = userId;
        this.clientMessageId = clientMessageId;
        this.emitter = emitter;
    }

    public boolean cancel() {
        if (finished.get()) {
            return false;
        }
        boolean first = cancelled.compareAndSet(false, true);
        closeUpstream();
        return first;
    }

    /**
     * 保证一次运行只向外发一次取消通知，避免 SSE 断连和用户点停止同时触发两次远程取消。
     */
    public boolean beginCancel() {
        return !finished.get() && cancelNotified.compareAndSet(false, true);
    }

    public void closeUpstream() {
        InputStream stream = upstream;
        if (stream != null) {
            try {
                stream.close();
            } catch (IOException ignored) {
                // 关闭流只用于打断阻塞读取，异常无需上抛。
            }
        }
    }

    public void markFinished() {
        finished.set(true);
    }

    public boolean isFinished() {
        return finished.get();
    }

    public boolean isCancelled() {
        return cancelled.get();
    }

    public void appendAnswer(String chunk) {
        answer.append(chunk);
    }

    public String partialAnswer() {
        return answer.toString();
    }

    public void attachUpstream(InputStream stream) {
        this.upstream = stream;
        if (cancelled.get()) {
            closeUpstream();
        }
    }

    public String getMessageId() {
        return messageId;
    }

    public String getSessionId() {
        return sessionId;
    }

    public String getUserId() {
        return userId;
    }

    public String getClientMessageId() {
        return clientMessageId;
    }

    public SseEmitter getEmitter() {
        return emitter;
    }
}
