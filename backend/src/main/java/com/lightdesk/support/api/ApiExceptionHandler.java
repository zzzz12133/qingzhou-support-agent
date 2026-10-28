package com.lightdesk.support.api;

import com.lightdesk.support.service.ApiException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.stream.Collectors;

@RestControllerAdvice
public class ApiExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(ApiException.class)
    public ResponseEntity<ApiDtos.ApiError> handleApi(ApiException exception) {
        ResponseEntity.BodyBuilder builder = ResponseEntity.status(exception.getStatus());
        if (exception.getRetryAfter() != null) {
            builder.header(HttpHeaders.RETRY_AFTER, String.valueOf(exception.getRetryAfter()));
        }
        return builder.body(new ApiDtos.ApiError(
                exception.getCode(),
                exception.getMessage(),
                exception.getRetryAfter(),
                exception.isRetryable()
        ));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiDtos.ApiError> handleValidation(MethodArgumentNotValidException exception) {
        String message = exception.getBindingResult().getFieldErrors().stream()
                .map(FieldError::getDefaultMessage)
                .collect(Collectors.joining("；"));
        if (message.isBlank()) {
            message = "请求参数不合法";
        }
        return ResponseEntity.badRequest()
                .body(new ApiDtos.ApiError("VALIDATION_ERROR", message, null, false));
    }

    @ExceptionHandler(SecurityException.class)
    public ResponseEntity<ApiDtos.ApiError> handleSecurity(SecurityException exception) {
        return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .body(new ApiDtos.ApiError("FORBIDDEN", exception.getMessage(), null, false));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ApiDtos.ApiError> handleIllegalArgument(IllegalArgumentException exception) {
        return ResponseEntity.badRequest()
                .body(new ApiDtos.ApiError("BAD_REQUEST", exception.getMessage(), null, false));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiDtos.ApiError> handleUnexpected(Exception exception) {
        log.error("未处理的请求异常", exception);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(new ApiDtos.ApiError("INTERNAL_ERROR", "服务暂时不可用，请稍后再试。", null, true));
    }
}
