---
schemaVersion: 1
contentModel: systemCriterion
contentModelVersion: 1

criterion:
  code: WEB-21
  slug: web-21
  title: HTTP 리디렉션
  severity:
    level: medium
    sourceLabel: 중

classification:
  domainIdentifier: web-service
  categoryIdentifier: web-service-security-configuration

targetScope: nonExhaustive
targetIdentifiers:
  - linux
sourceTargetText: "Apache, Nginx, IIS, WebtoB"

provenance:
  sourceDocumentIdentifier: kisa-cce-criteria-2026
  sourcePageRanges:
    - physicalPageStart: 334
      physicalPageEnd: 337
      printedPageStart: "334"
      printedPageEnd: "337"

sourceAnnotations:
  - annotationIdentifier: web-21-source-001
    annotationType: sourceDuplication
    targetType: astNode
    targetReference: "web-21:remediation.linux.step:2"
    sourceLocation:
      physicalPage: 334
      printedPage: "334"
      pageRegionIdentifier: p334-web-21
    sourceText: "SSL 인증서 활성화 설정"
    explanation: "Apache 절차에서 Step 1 번호가 연속으로 두 번 사용된다. 문서 순서를 보존하기 위해 두 번째 항목을 순서 목록의 2번으로 표현했다."
    disposition: unresolved
    reviewStatus: pending
    verificationEvidence:
      - "PDF physical page 334의 Apache 절차 번호를 확인했다."
    reviewedBy: null
    reviewedAt: null
    approvedBy: null
    approvedAt: null
  - annotationIdentifier: web-21-source-002
    annotationType: sourceInconsistency
    targetType: astNode
    targetReference: "web-21:remediation.linux.command:5"
    sourceLocation:
      physicalPage: 335
      printedPage: "335"
      pageRegionIdentifier: p335-web-21
    sourceText: "vi sudo a2ensite default-ssl"
    explanation: "가상 호스트 활성화 단계의 명령에 vi와 sudo가 함께 표기되어 있다. 원문을 수정하지 않고 보존했다."
    disposition: unresolved
    reviewStatus: pending
    verificationEvidence:
      - "PDF physical page 335의 Apache Step 5 명령을 확인했다."
    reviewedBy: null
    reviewedAt: null
    approvedBy: null
    approvedAt: null
  - annotationIdentifier: web-21-source-003
    annotationType: sourceInconsistency
    targetType: astNode
    targetReference: "web-21:remediation.linux.step:8"
    sourceLocation:
      physicalPage: 335
      printedPage: "335"
      pageRegionIdentifier: p335-web-21
    sourceText: "SSL 활성화 설정"
    explanation: "SSL 활성화 설정 단계에 제시된 블록은 80번 포트와 HTTPS 리디렉션만 포함하며 SSL 수신 설정은 제시하지 않는다."
    disposition: unresolved
    reviewStatus: pending
    verificationEvidence:
      - "PDF physical page 335의 Nginx Step 2 제목과 설정 블록을 대조했다."
    reviewedBy: null
    reviewedAt: null
    approvedBy: null
    approvedAt: null
  - annotationIdentifier: web-21-source-004
    annotationType: sourceInconsistency
    targetType: astNode
    targetReference: "web-21:remediation.linux.command:11"
    sourceLocation:
      physicalPage: 337
      printedPage: "337"
      pageRegionIdentifier: p337-web-21
    sourceText: "/[WebtoB 설치 디렉터리]/config/rewrite_ssel.conf"
    explanation: "앞선 URLRewriteConfig 값은 config/rewrite_ssl.conf이지만 Step 3과 Step 4의 파일명은 rewrite_ssel.conf로 표기되어 있다. 원문 철자를 보존했다."
    disposition: unresolved
    reviewStatus: pending
    verificationEvidence:
      - "PDF physical pages 336-337의 URLRewriteConfig 값과 편집 경로를 대조했다."
    reviewedBy: null
    reviewedAt: null
    approvedBy: null
    approvedAt: null
---

## 개요

### 점검 내용

웹 서비스 접근 시 HTTP Redirection 활성화 여부 점검

### 점검 목적

HTTP 차단 및 HTTPS로 Redirection 활성화를 통해 평문으로 전송되는 데이터를 암호화하여 공격자의 데이터 스니핑에 대비하기 위함

### 보안 위협

HTTP 통신은 암호화 전송이 아닌 평문 전송을 하므로 공격자가 스니핑을 시도할 경우 관리자의 ID, 비밀번호가 노출되어 악의적 사용자가 관리자 계정을 탈취할 수 있는 위험이 존재함

### 참고

> **참고**
>
> -

## 점검 대상 및 판단 기준

### 대상

Apache, Nginx, IIS, WebtoB

### 판단 기준

- **양호:** HTTP 접근 시 HTTPS Redirection이 활성화된 경우
- **취약:** HTTP 접근 시 HTTPS Redirection이 비활성화된 경우

### 조치 방법

HTTP Redirection 활성화 설정

### 조치 시 영향

일반적인 경우 영향 없음

## 점검 및 조치 사례

### LINUX

**Apache**

1. SSL 모듈 활성화 확인

   ```shell command
   # apache2ctl -M | grep ssl
   ```

2. SSL 인증서 활성화 설정

3. (미설치 시) mod_rewrite 설치

   ```shell command
   # apt install mod_ssl
   ```

4. HTTP Redirection 설정 확인

   ```shell command
   # vi /[Apache 설치 디렉터리]/sites-available/default-ssl.conf
   ```

   ```apache configuration
   <VirtualHost *:80>
       ServerName example.com
       Redirect permanent / https://example.com/
   </VirtualHost>
   ```

5. SSL 가상 호스트 설정

   ```shell command
   # vi /[Apache 설치 디렉터리]/sites-available/default-ssl.conf
   ```

   ```apache configuration
   <VirtualHost *:80>
       ServerAdmin webmaster@yourdomain.com
       ServerName yourdomain.com
       DocumentRoot /var/www/html
       RewriteEngine On
       RewriteCond %{HTTPS} off
       RewriteRule ^ https://%{HTTP_HOST}%{REQUEST_URI} [L,R=301]
       ErrorLog ${APACHE_LOG_DIR}/error.log
       CustomLog ${APACHE_LOG_DIR}/access.log combined
   </VirtualHost>
   ```

6. SSL 가상 호스트 활성화 및 Apache 재구동

   ```shell command
   # vi sudo a2ensite default-ssl
   # systemctl restart apache2
   ```

**Nginx**

1. Server 블록 내 HTTPS Redirection 설정 확인

   ```shell command
   # vi /[Nginx 설치 디렉터리]/sites-available/default
   ```

   ```nginx configuration
   server {
       listen 80;
       server_name yourdomain.com www.yourdomain.com;
       return 301 https://$host$request_uri;
   }
   ```

2. SSL 활성화 설정

   ```shell command
   # vi /[Nginx 설치 디렉터리]/sites-available/default
   ```

   ```nginx configuration
   server {
       listen 80;
       server_name mydomain.com www.mydomain.com;
       return 301 https://$host$request_uri;
   }
   ```

3. Nginx 재구동

   ```shell command
   # systemctl restart nginx
   ```

**IIS**

1. SSL 인증서 활성화

   SSL 인증서 등록 과정에서 사이트 바인딩 `종류`를 HTTPS로 설정

2. 등록된 SSL 인증서 바인딩 설정 확인

   제어판 > 관리 도구 > IIS(인터넷 정보 서비스) 관리자 > 해당 웹사이트 > [사이트 바인딩] > [편집] 탭 > SSL 인증서 확인

3. IIS 서버 재구동

**WebtoB**

1. Server 설정 파일 NODE절 vhost의 URLRewrite, URLRewriteConfig 설정 확인

   ```shell command
   # vi /[WebtoB 설치 디렉터리]/config/http.m
   ```

   ```text configuration
   *VHOST
   vhost1             ...
       URLRewrite = Y,
       URLRewriteConfig = "config/rewrite_ssl.conf",
   ```

2. Server 설정 파일 NODE절 vhost의 URLRewrite, URLRewriteConfig 설정

   ```shell command
   # vi /[WebtoB 설치 디렉터리]/config/http.m
   ```

   ```text configuration
   *VHOST
   vhost1             ...
       URLRewrite = Y,
       URLRewriteConfig = "config/rewrite_ssl.conf",
   ```

3. URLRewriteConfig 파일에서 Redirection 확인

   ```shell command
   # vi /[WebtoB 설치 디렉터리]/config/rewrite_ssel.conf
   ```

   ```text configuration
   RewriteCond %{HTTPS} off
   RewriteRule .* https://%{SERVER_NAME}%{REQUEST_URI} [R=307,L]
   ```

4. URLRewriteConfig 파일에서 Redirection 설정

   ```shell command
   # vi /[WebtoB 설치 디렉터리]/config/rewrite_ssel.conf
   ```

   ```text configuration
   RewriteCond %{HTTPS} off
   RewriteRule .* https://%{SERVER_NAME}%{REQUEST_URI} [R=307,L]
   ```

5. 설정 파일 컴파일 및 재구동

   ```shell command
   # wscfl -I http.m
   # wsdown
   # wsboot
   ```
