package com.lightdesk.support;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.lightdesk.support.config.AppProperties;
import com.lightdesk.support.model.ChatMessage;
import com.lightdesk.support.model.Session;
import com.lightdesk.support.store.SessionStore;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class SessionStoreTest {

    @TempDir
    Path tempDir;

    private SessionStore newStore() {
        AppProperties properties = new AppProperties();
        properties.setDataDir(tempDir.toString());
        return new SessionStore(new ObjectMapper(), properties);
    }

    @Test
    void persistsSessionAndMessagesAcrossReload() {
        SessionStore store = newStore();
        Session session = store.create("demo-user", null);
        store.appendUser(session, "帮我查一下 A1001 的物流");
        store.appendAssistant(
                session,
                "assistant-1",
                "包裹正在运输中。",
                "done",
                Map.of("provider", "本地演示模型")
        );

        SessionStore reloaded = newStore();
        Session loaded = reloaded.get(session.getId(), "demo-user");
        assertThat(loaded).isNotNull();
        assertThat(loaded.getTitle()).contains("帮我查");
        assertThat(loaded.getMessages()).hasSize(2);
        ChatMessage assistant = loaded.getMessages().get(1);
        assertThat(assistant.getId()).isEqualTo("assistant-1");
        assertThat(assistant.getMetadata()).containsEntry("provider", "本地演示模型");

        List<?> sessions = reloaded.list("demo-user");
        assertThat(sessions).hasSize(1);
        assertThat(reloaded.list("another-user")).isEmpty();
    }

    @Test
    void rejectsCrossUserAccess() {
        SessionStore store = newStore();
        Session session = store.create("alice", null);
        assertThatThrownBy(() -> store.get(session.getId(), "bob"))
                .isInstanceOf(SecurityException.class);
    }

    @Test
    void rejectsInvalidSessionId() {
        SessionStore store = newStore();
        assertThatThrownBy(() -> store.get("../../etc/passwd", "alice"))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
