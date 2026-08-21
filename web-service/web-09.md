---
schemaVersion: 1
contentModel: systemCriterion
contentModelVersion: 1

criterion:
  code: WEB-09
  slug: web-09
  title: 웹 서비스 프로세스 권한 제한
  severity:
    level: high
    sourceLabel: 상

classification:
  domainIdentifier: web-service
  categoryIdentifier: web-service-service-management

targetScope: nonExhaustive
targetIdentifiers:
  - linux
sourceTargetText: "Apache, Tomcat, Nginx, IIS, JEUS, WebtoB"

provenance:
  sourceDocumentIdentifier: kisa-cce-criteria-2026
  sourcePageRanges:
    - physicalPageStart: 295
      physicalPageEnd: 299
      printedPageStart: "295"
      printedPageEnd: "299"

sourceAnnotations:
  - annotationIdentifier: web-09-source-001
    annotationType: sourceTypographicalError
    targetType: document
    targetReference: "web-09"
    sourceLocation:
      physicalPage: 296
      printedPage: "296"
      pageRegionIdentifier: p296-web-09
    sourceText: "# usermod –s /sbin/nologin [사용자명]"
    explanation: "Nginx 명령의 옵션 앞 문자가 일반 하이픈(-)이 아닌 대시(–)로 표기되어 있다."
    disposition: unresolved
    reviewStatus: pending
    verificationEvidence:
      - "PDF physical page 296의 Nginx Step 3 명령을 확인했다."
    reviewedBy: null
    reviewedAt: null
    approvedBy: null
    approvedAt: null
  - annotationIdentifier: web-09-source-002
    annotationType: sourceTypographicalError
    targetType: document
    targetReference: "web-09"
    sourceLocation:
      physicalPage: 299
      printedPage: "299"
      pageRegionIdentifier: p299-web-09
    sourceText: "FileName = \"/home/tmax/webtob/log/system.log>"
    explanation: "LOGGING 예시의 FileName 값 세 곳에서 닫는 큰따옴표가 꺾쇠괄호 또는 다른 문자로 표기되어 있다. 원문을 그대로 보존했다."
    disposition: unresolved
    reviewStatus: pending
    verificationEvidence:
      - "PDF physical page 299의 LOGGING 예시를 확인했다."
    reviewedBy: null
    reviewedAt: null
    approvedBy: null
    approvedAt: null
  - annotationIdentifier: web-09-source-003
    annotationType: sourceInconsistency
    targetType: document
    targetReference: "web-09"
    sourceLocation:
      physicalPage: 298
      printedPage: "298"
      pageRegionIdentifier: p298-web-09
    sourceText: "# mv /[JEUS 설치 디렉터리]/home/jeus"
    explanation: "mv 명령에 원본과 대상 중 하나만 기재되어 있어 실행에 필요한 인수가 불완전하다."
    disposition: unresolved
    reviewStatus: pending
    verificationEvidence:
      - "PDF physical page 298의 JEUS Step 2 명령을 확인했다."
    reviewedBy: null
    reviewedAt: null
    approvedBy: null
    approvedAt: null
  - annotationIdentifier: web-09-source-004
    annotationType: sourceTypographicalError
    targetType: document
    targetReference: "web-09"
    sourceLocation:
      physicalPage: 299
      printedPage: "299"
      pageRegionIdentifier: p299-web-09
    sourceText: "# wscfl –i http.m"
    explanation: "옵션 앞 문자가 일반 하이픈(-)이 아닌 대시(–)로 표기되어 있다."
    disposition: unresolved
    reviewStatus: pending
    verificationEvidence:
      - "PDF physical page 299의 WebtoB Step 6 명령을 확인했다."
    reviewedBy: null
    reviewedAt: null
    approvedBy: null
    approvedAt: null
---

## 개요

### 점검 내용

웹 서비스 프로세스의 관리자 권한 구동 여부 점검

### 점검 목적

웹 프로세스가 웹 서비스 운영에 필요한 최소한의 권한만을 갖도록 제한함으로써 웹 사이트 방문자가 웹 서비스의 취약점을 이용해 시스템에 대한 어떤 권한도 획득할 수 없도록 하여 침해사고 발생 시 피해 범위 확산을 방지하기 위함

### 보안 위협

웹 프로세스 권한을 제한하지 않은 경우, 웹 사이트 방문자가 웹 서비스의 취약점을 이용하여 시스템 권한을 획득할 수 있으며, 웹 취약점을 통해 접속 권한을 획득한 경우에는 관리자 권한을 획득하여 서버에 접속 후 정보의 변경, 훼손 및 유출될 위험이 존재함

### 참고

> **참고**
>
> -

## 점검 대상 및 판단 기준

### 대상

Apache, Tomcat, Nginx, IIS, JEUS, WebtoB

### 판단 기준

- **양호:** 웹 프로세스(웹 서비스)가 관리자 권한이 부여된 계정이 아닌 운영에 필요한 최소한의 권한을 가진 별도의 계정으로 구동되고 있는 경우
- **취약:** 웹 프로세스(웹 서비스)가 관리자 권한이 부여된 계정으로 구동되고 있는 경우

### 조치 방법

웹 서비스 프로세스 구동 시 관리자 권한이 아닌 운영에 필요한 최소한의 권한을 가진 계정으로 구동 설정

### 조치 시 영향

일반적인 경우 영향 없음

## 점검 및 조치 사례

### LINUX

**Apache**

1. `envvars` 파일 내 실행 계정을 관리자 계정이 아닌 별도의 계정으로 변경

   ```shell command
   # vi /[Apache 설치 디렉터리]/envvars
   ```

   ```text configuration
   export APACHE_RUN_USER=www-data
   export APACHE_RUN_GROUP=www-data
   ```

2. Apache 서비스 파일 소유권 변경

   ```shell command
   # chown -R www-data:www-data /etc/apache2/
   # chown -R www-data:www-data /var/www/
   # chown -R www-data:www-data /var/log/apache2/
   ```

3. 웹 서비스 실행 계정 로그인 제한 설정

   ```shell command
   # usermod -s /sbin/nologin [사용자명]
   ```

4. Apache 재구동

   ```text command
   # systemctl restart apache2 또는 httpd
   ```

**Tomcat**

1. `tomcat.service` 파일 내 Tomcat 데몬 구동 권한을 관리자 계정이 아닌 별도 계정으로 변경

   ```shell command
   # vi /etc/systemd/system/tomcat.service
   ```

   ```ini configuration
   [Service]
   User=tomcat
   Group=tomcat
   ```

2. Tomcat 서비스 파일 소유권 변경

   ```shell command
   # chown -R tomcat:tomcat /[Tomcat 설치 디렉터리]/usr/share/tomcat9/
   # chown -R tomcat:tomcat /[Tomcat 설치 디렉터리]/tomcat9/temp
   # chown -R tomcat:tomcat / [Tomcat 설치 디렉터리]/logs
   # chown -R tomcat:tomcat /usr/share/tomcat9/webapps
   # chown -R tomcat:tomcat /usr/share/tomcat9/work
   ```

3. 웹서비스 실행 계정 로그인 제한 설정

   ```shell command
   # usermod -s /sbin/nologin [사용자명]
   ```

4. Tomcat 서비스 재구동

   ```shell command
   # systemctl restart tomcat
   ```

**Nginx**

1. `nginx.conf` 파일 내 Nginx 데몬 구동 권한을 관리자 계정이 아닌 별도 계정으로 변경

   ```shell command
   # vi /[Nginx 설치 디렉터리]/conf/nginx.conf
   ```

   ```nginx configuration
   User nginx nginx;
   ```

2. Nginx 전용 계정 생성 및 Nginx 전용 그룹 추가

   ```shell command
   # adduser --system --no-create-home --shell /bin/false nginx
   # groupadd nginx && sudo usermod -aG nginx nginx
   ```

3. 웹서비스 실행 계정 로그인 제한 설정

   ```shell command
   # usermod –s /sbin/nologin [사용자명]
   ```

4. Nginx 서비스 재구동

   ```shell command
   # systemctl restart nginx
   ```

**IIS**

1. 웹 사이트 응용프로그램 풀 이름 확인

   ```text literal
   제어판 > 관리 도구 > 인터넷 정보 서비스(IIS) 관리자 > 해당 웹 사이트 > 고급 설정 > ‘응용프로그램 풀 이름(DefaultAppPool)’ 확인
   ```

2. 웹 사이트 응용프로그램 풀 ID 확인

   ```text literal
   제어판 > 관리 도구 > 인터넷 정보 서비스(IIS) 관리자 > 응용프로그램 풀 > ‘응용프로그램 풀 이름(DefaultAppPool)’ 선택 > 고급 설정 > ID > 확인
   ```

3. 웹사이트 응용프로그램 풀 ID 설정

   ```text literal
   제어판 > 관리 도구 > 인터넷 정보 서비스(IIS) 관리자 > 응용프로그램 풀 > ‘응용 프로그램 풀 이름(DefaultAppPool)’ 선택 > 고급 설정 > ID > ApplicationPoolIdentity 선택
   ```

**JEUS**

1. JEUS 데몬 구동 권한 확인

   ```shell command
   # ps –ef |grep jeus
   ```

   ```text output
   jeus 25305 4223 99 09:54 pts/5 00:03:31 /usr/lib/jvm/java-11-openjdk-amd64/bin/java-DadminServer...
   ```

2. JEUS 데몬 구동 권한을 관리자 계정이 아닌 별도 계정으로 변경

   ```shell command
   # useradd –m jeus
   # mv /[JEUS 설치 디렉터리]/home/jeus
   ```

3. `[JEUS 설치 디렉터리]` 소유자 및 그룹 소유자를 JEUS 계정으로 변경

   ```shell command
   # chown –R jeus:jeus /home/jeus/
   ```

**WebtoB**

1. 소유자 및 그룹 소유자 변경

   ```shell command
   chown –R [WebtoB 전용 계정]:[WebtoB 전용 계정] /[WebtoB 디렉터리]
   ```

2. `http.m` 파일 내 기존 경로 변경: `NODE`절의 `WEBTOBDIR`, `DOCROOT`을 변경한 디렉터리로 설정하고, `ALIAS`절의 `alias1`을 변경한 디렉터리로 설정하며, `LOGGING`절의 `syslog`, `log1`, `log2`을 변경한 디렉터리로 설정

   ```text configuration
   *NODE
   imuser  WEBTOBDIR="/home/tmax/webtob/",
           SHMKEY = 54000,
           DOCROOT="/home/tmax/webtob/docs",
   ```

   ```text configuration
   *ALIAS
   alias1  URI = "/cgi-bin/", RealPath = "/home/webtob/webtob/cgi-bin/"
   ```

   ```text configuration
   *LOGGING
   syslog  Format = "SYSLOG", FileName = "/home/tmax/webtob/log/system.log>
           Option = "sync"
   log1    Format = "DEFAULT", FileName = "/home/tmax/webtob/log/access.lo>
           Option = "sync"
   log2    Format = "ERROR", FileName = "/home/tmax/webtob/log/error.log_%>
           Option = "sync"
   ```

3. 변경한 디렉터리명 환경변수에 추가

   ```shell command
   # export WEBTOB=/[WebtoB 디렉터리]
   # source ~/.bashrc
   ```

4. `libwbiconv.so` 파일을 직접 `/usr/lib`로 복사

   ```shell command
   # cp /webtob/lib/libwbiconv.so /usr/lib/
   ```

5. 라이브러리 캐시 업데이트

   ```shell command
   # ldconfig
   ```

6. 설정 파일 컴파일

   ```shell command
   # wscfl –i http.m
   ```
