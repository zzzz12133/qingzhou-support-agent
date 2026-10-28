package com.lightdesk.support;

import com.lightdesk.support.config.AppProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(AppProperties.class)
public class SupportBotApplication {

    public static void main(String[] args) {
        SpringApplication.run(SupportBotApplication.class, args);
    }
}
