---
schemaVersion: 1
contentModel: systemCriterion
contentModelVersion: 1

criterion:
  code: WEB-10
  slug: web-10
  title: 불필요한 프록시 설정 제한
  severity:
    level: high
    sourceLabel: 상

classification:
  domainIdentifier: web-service
  categoryIdentifier: web-service-service-management

targetScope: nonExhaustive
targetIdentifiers:
  - solaris
  - linux
  - aix
  - hp-ux
sourceTargetText: "Apache, Tomcat, Nginx, IIS, JEUS, WebtoB"

provenance:
  sourceDocumentIdentifier: kisa-cce-criteria-2026
  sourcePageRanges:
    - physicalPageStart: 300
      physicalPageEnd: 302
      printedPageStart: "300"
      printedPageEnd: "302"

sourceAnnotations:
  - annotationIdentifier: web-10-source-001
    annotationType: sourceTypographicalError
    targetType: document
    targetReference: "kisa-cce-criteria-2026"
    sourceLocation:
      physicalPage: 301
      printedPage: "301"
      pageRegionIdentifier: p301-web-10
    sourceText: "# cat /[Nginx 설치 디렉터리/nginx.conf"
    explanation: "경로 표기에서 여는 대괄호에 대응하는 닫는 대괄호가 보이지 않는다. 원문을 그대로 보존했다."
    disposition: unresolved
    reviewStatus: pending
    verificationEvidence:
      - "PDF physical page 301의 Nginx 명령을 확인했다."
    reviewedBy: null
    reviewedAt: null
    approvedBy: null
    approvedAt: null
  - annotationIdentifier: web-10-source-002
    annotationType: sourceInconsistency
    targetType: document
    targetReference: "kisa-cce-criteria-2026"
    sourceLocation:
      physicalPage: 301
      printedPage: "301"
      pageRegionIdentifier: p301-web-10
    sourceText: "# vi /[WebtoB 설치 디렉터리]/ReverseProxy/WEB-INF/web.xml"
    explanation: "JEUS 절차에 WebtoB 설치 디렉터리 경로가 제시되어 있다. 원문을 그대로 보존했다."
    disposition: unresolved
    reviewStatus: pending
    verificationEvidence:
      - "PDF physical page 301의 JEUS 절차 제목과 명령 경로를 대조했다."
    reviewedBy: null
    reviewedAt: null
    approvedBy: null
    approvedAt: null
---

## 개요

### 점검 내용

웹 서비스 불필요한 Proxy 설정제한 여부 점검

### 점검 목적

불필요한 Proxy 설정을 제한하여 자원 낭비 예방 및 관리의 복잡성을 감소시키며, 중간자 공격 등의 해킹 공격으로부터 시스템 관련 정보가 노출되거나 악용되는 것을 방지하기 위함

### 보안 위협

불필요한 Proxy 설정을 제한하지 않는 경우 공격자가 Proxy 서버를 이용하여 원래 의도되지 않은 방식으로 시스템에 접근하거나 시스템 관련 정보가 유출될 위험이 존재함

### 참고

> **참고**
>
> -

## 점검 대상 및 판단 기준

### 대상

Apache, Tomcat, Nginx, IIS, JEUS, WebtoB

### 판단 기준

- **양호:** 불필요한 Proxy 설정을 제한한 경우
- **취약:** 불필요한 Proxy 설정을 제한하지 않은 경우

### 조치 방법

불필요한 Proxy 설정 존재 여부 점검 및 제한 설정

### 조치 시 영향

일반적인 경우 영향 없음

## 점검 및 조치 사례

### LINUX

1. **Apache:** `apache2.conf` (또는 `/conf/httpd.conf`) 파일 내 불필요한 Proxy 제거

   ```apache configuration
   <VirtualHost *:80>
       ServerName www.example.com
       ProxyPreserveHost On
       ProxyRequests Off
       ProxyPass / http://backend-server.example.com/
       ProxyPassReverse / http://backend-server.example.com/
   </VirtualHost>
   ```

2. **Tomcat:** `server.xml` 파일 내 Connector 요소에서 불필요한 Proxy 설정 제거

   ```xml configuration
   <Connector port="8080" protocol="HTTP/1.1"
       redirectPort="8443"
       proxyName="proxy.example.com"
       proxyPort="80" />
   ```

3. **Nginx:** `nginx.conf` 파일 내 웹 사이트에서 불필요한 Proxy 설정 제거

   ```shell command
   # cat /[Nginx 설치 디렉터리/nginx.conf
   ```

   ```nginx configuration
   location / {
       proxy_pass http://backendserver:8080;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
   }
   ```

4. **IIS:** 제어판 > 관리 도구 > 인터넷 정보 서비스(IIS) 관리자 > 해당 웹 사이트 > 루트 디렉터리에서 불필요한 Proxy 설정 제거

   ```xml configuration
   <?xml version="1.0" encoding="UTF-8"?>
   <configuration>
       <system.webServer>
           <directoryBrowse enabled="true" />
       </system.webServer>
   </configuration>
   ```

   ```text literal
   [ Proxy 설정 확인 및 제거 ]
   ```

5. **JEUS:** `web.xml` 파일 내 불필요한 Proxy 제거

   ```shell command
   # vi /[WebtoB 설치 디렉터리]/ReverseProxy/WEB-INF/web.xml
   ```

6. **WebtoB:** `http.m` 파일 내 불필요 Proxy 설정 제거

   ```shell command
   # vi /[WebtoB 디렉터리]/conf/http.m
   ```

   ```text configuration
   REVERSE_PROXY(0): Name = rproxy1,
       PathPrefix = "/proxypath/",
       ServerAddress = "127.0.0.1:8088",
   ```
