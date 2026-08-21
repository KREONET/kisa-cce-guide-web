---
schemaVersion: 1
contentModel: webApplicationCriterion
contentModelVersion: 1

criterion:
  code: EP
  slug: ep
  title: 에러 페이지 적용 미흡
  severity:
    level: high
    sourceLabel: 상

classification:
  domainIdentifier: web-application
  categoryIdentifier: web-application-error-page

targetScope: nonExhaustive
targetIdentifiers:
  - linux
sourceTargetText: "웹 애플리케이션 서버, 웹 방화벽"

provenance:
  sourceDocumentIdentifier: kisa-cce-criteria-2026
  sourcePageRanges:
    - physicalPageStart: 703
      physicalPageEnd: 707
      printedPageStart: "703"
      printedPageEnd: "707"

sourceAnnotations: []
---

## 개요

### 점검 내용

웹 애플리케이션 에러 페이지 내 불필요한 정보 노출 여부 점검

### 점검 목적

사용자 정의 에러 페이지를 설정하여 기본 서버 에러 페이지 내 불필요한 정보(서버 버전 정보, 시스템 절대 경로, 스택 트레이스 등)의 제공을 차단하기 위함

### 보안 위협

에러 페이지 내 서버 및 응용 시스템의 상세한 정보를 포함한 경우, 시스템 구조와 스택 트레이스, 데이터베이스 쿼리 등 민감한 정보를 노출시켜 공격 벡터로 악용할 가능성 존재

### 참고

> **참고**
>
> 소스코드 및 취약점 점검 필요

## 점검 대상 및 판단 기준

### 대상

웹 애플리케이션 서버, 웹 방화벽

### 판단 기준

- **양호:** 에러 발생 시 자체 정의 에러 페이지를 출력하여 과도한 정보가 노출되지 않는 경우
- **취약:** 에러 발생 시 기본 에러 페이지가 출력되며, 해당 페이지에 불필요한 정보(서버 버전 정보, 시스템 경로, 스택 트레이스 등)가 노출되는 경우

### 조치 방법

웹 애플리케이션 서버 내 사용자 정의 에러 페이지를 적용함으로써 불필요한 정보 노출 방지

### 조치 시 영향

일반적인 경우 영향 없음

## 점검 및 조치 사례

### LINUX

1. **Apache:** `apache2.conf` 또는 `httpd.conf` 파일 내 아래 지시자 추가 후 서버 재기동

   ```apache configuration
   ...
   ServerTokens Prod
   ServerSignature Off
   ...
   ```

2. **Apache:** 사용자 에러 페이지 정의

   ```apache configuration
   # 예) ErrorDocument 404 /main/error.html
   ErrorDocument 404 [에러 페이지 경로]
   ErrorDocument 405 [에러 페이지 경로]
   # 추가적으로 에러 코드 등록하여 설정
   ...
   ```

3. **Tomcat:** `server.xml` 파일 내 `<Connector>` 요소에 아래 지시자 추가 후 서버 재기동

   ```xml configuration
   <Connector port="8080" protocol="HTTP/1.1"
              connectionTimeout="20000"
              redirectPort="8443"
              maxParameterCount="1000"
              server=""
   />
   ```

4. **Tomcat:** `server.xml` 파일 내 아래 지시자 추가 후 서버 재기동하여 개발용 리포트 비활성화

   ```xml configuration
   <Valve className="org.apache.catalina.valves.ErrorReportValve"
          showReport="false"
          showServerInfo="false" />
   </Host>
   ```

5. **Tomcat:** `web.xml`에 에러 페이지 매핑

   ```xml configuration
   <!-- web.xml -->
   <error-page>
     <error-code>404</error-code>
     <location>/errors/404</location>
   </error-page>

   <error-page>
     <error-code>500</error-code>
     <location>/errors/500</location>
   </error-page>

   <!-- 모든 예외(최상위) 공통 500 처리 -->
   <error-page>
     <exception-type>java.lang.Exception</exception-type>
     <location>/errors/500</location>
   </error-page>
   ```

6. **Nginx:** `nginx.conf` 파일 내 아래 지시자 추가 후 서버 재기동

   ```nginx configuration
   ...
   http {
       server_tokens off;
       ...
   }
   ...
   ```

7. **Nginx:** `/etc/nginx/sites-available/default` 파일 내 아래 지시자 추가 후 서버 재기동

   ```nginx configuration
   server {
       listen 80;
       ...
       # 기타 설정
       ...
       error_page 400 401 402 405 /custom_4xx.html;
       error_page 404 /custom_404.html;
       error_page 500 502 503 504 /custom_5xx.html;
       location = /custom_404.html {
           root /var/www/html;
           internal;
       }

       location = /custom_4xx.html {
           root /var/www/html;
           internal;
       }

       location = /custom_5xx.html {
           root /var/www/html;
           internal;
       }
       ...
   }
   ```

8. **IIS (6.0 이하):** 응답 헤더의 서버 버전 제거 제한 확인

   ```text literal
   Microsoft사의 URLScan 3.1 도구 지원 종료로 인한 서버 버전 제거 제한
   ```

9. **IIS (6.0 이하):** 인터넷 정보 서비스 → 등록 정보 → 사용자 정의 오류 → 등록 정보 편집 → 별도 에러 페이지 지정
10. **IIS (7.0 이상):** URL Rewrite 모듈 설치 → IIS 관리자 → URL 재작성 → 서버 변수 보기 → 추가 → `RESPONSE_SERVER` 변수 추가 → 규칙 추가 → 아웃바운드 규칙(빈 규칙) → 규칙 추가 → 적용
11. **IIS (7.0 이상):** URL Rewrite 모듈(`https://www.iis.net/downloads/microsoft/url-rewrite`)
12. **IIS (7.0 이상):** IIS 관리자 → 오류 페이지 → 기능 설정 편집 → 사용자 지정 오류 페이지

### 추가 지침

1. 에러 유도 시 에러 페이지 내 불필요한 정보(서버 버전 정보, 시스템 절대 경로, 스택 트레이스 등)가 노출되는지 확인
