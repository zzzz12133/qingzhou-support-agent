package com.lightdesk.support.service;

import com.lightdesk.support.config.AppProperties;
import org.springframework.stereotype.Component;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.HashMap;
import java.util.Map;

@Component
public class RateLimiter {

    private static final long WINDOW_NANOS = 60_000_000_000L;

    private final int limit;
    private final Map<String, Deque<Long>> windows = new HashMap<>();

    public RateLimiter(AppProperties properties) {
        this.limit = Math.max(1, properties.getRateLimitPerMinute());
    }

    public synchronized Decision allow(String userId) {
        long now = System.nanoTime();
        Deque<Long> hits = windows.computeIfAbsent(userId, key -> new ArrayDeque<>());
        while (!hits.isEmpty() && now - hits.peekFirst() >= WINDOW_NANOS) {
            hits.pollFirst();
        }
        if (hits.size() >= limit) {
            long oldest = hits.peekFirst() == null ? now : hits.peekFirst();
            int retryAfter = (int) Math.max(1, Math.ceil((WINDOW_NANOS - (now - oldest)) / 1_000_000_000.0));
            return new Decision(false, 0, retryAfter);
        }
        hits.addLast(now);
        return new Decision(true, limit - hits.size(), 0);
    }

    public synchronized void reset(String userId) {
        windows.remove(userId);
    }

    public record Decision(boolean allowed, int remaining, int retryAfterSeconds) {
    }
}
