package com.lightdesk.support.api;

import com.lightdesk.support.service.ChatService;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequestMapping("/api/chat")
public class ChatController {

    private final ChatService chatService;

    public ChatController(ChatService chatService) {
        this.chatService = chatService;
    }

    @PostMapping(value = "/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter stream(@Valid @RequestBody ApiDtos.ChatRequest request) {
        return chatService.start(request);
    }

    @PostMapping("/{messageId}/cancel")
    public ApiDtos.CancelResponse cancel(
            @PathVariable String messageId,
            @Valid @RequestBody ApiDtos.CancelRequest request
    ) {
        boolean cancelled = chatService.cancel(messageId, request.userId());
        return new ApiDtos.CancelResponse(
                cancelled,
                cancelled ? "已停止生成" : "该消息已经结束或不存在"
        );
    }
}
