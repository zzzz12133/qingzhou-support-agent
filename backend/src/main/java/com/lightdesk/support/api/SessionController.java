package com.lightdesk.support.api;

import com.lightdesk.support.model.Session;
import com.lightdesk.support.model.SessionSummary;
import com.lightdesk.support.service.ChatService;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/sessions")
public class SessionController {

    private final ChatService chatService;

    public SessionController(ChatService chatService) {
        this.chatService = chatService;
    }

    @GetMapping
    public Map<String, Object> list(
            @RequestParam(defaultValue = "demo-user") String userId
    ) {
        List<SessionSummary> sessions = chatService.listSessions(userId);
        return Map.of("sessions", sessions);
    }

    @PostMapping
    public Session create(@Valid @RequestBody ApiDtos.CreateSessionRequest request) {
        return chatService.createSession(request.userId(), request.title());
    }

    @GetMapping("/{sessionId}")
    public Session detail(
            @PathVariable String sessionId,
            @RequestParam(defaultValue = "demo-user") String userId
    ) {
        return chatService.getSession(sessionId, userId);
    }

    @GetMapping("/{sessionId}/memory")
    public Map<String, Object> memory(
            @PathVariable String sessionId,
            @RequestParam(defaultValue = "demo-user") String userId
    ) {
        return chatService.sessionMemory(sessionId, userId);
    }

    @DeleteMapping("/{sessionId}")
    public ResponseEntity<Void> delete(
            @PathVariable String sessionId,
            @RequestParam(defaultValue = "demo-user") String userId
    ) {
        chatService.deleteSession(sessionId, userId);
        return ResponseEntity.noContent().build();
    }
}
