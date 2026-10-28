package com.lightdesk.support.api;

import com.lightdesk.support.service.ChatService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api")
public class SystemController {

    private final ChatService chatService;

    public SystemController(ChatService chatService) {
        this.chatService = chatService;
    }

    @GetMapping("/health")
    public Map<String, Object> health() {
        return chatService.health();
    }

    @GetMapping("/system/runtime")
    public Map<String, Object> runtime() {
        return chatService.runtime();
    }
}
