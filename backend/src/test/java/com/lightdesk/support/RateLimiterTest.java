package com.lightdesk.support;

import com.lightdesk.support.config.AppProperties;
import com.lightdesk.support.service.RateLimiter;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class RateLimiterTest {

    @Test
    void limitsPerUserInSlidingWindow() {
        AppProperties properties = new AppProperties();
        properties.setRateLimitPerMinute(2);
        RateLimiter limiter = new RateLimiter(properties);

        assertThat(limiter.allow("alice").allowed()).isTrue();
        assertThat(limiter.allow("alice").allowed()).isTrue();
        RateLimiter.Decision blocked = limiter.allow("alice");
        assertThat(blocked.allowed()).isFalse();
        assertThat(blocked.retryAfterSeconds()).isGreaterThan(0);
        assertThat(limiter.allow("bob").allowed()).isTrue();
    }
}
