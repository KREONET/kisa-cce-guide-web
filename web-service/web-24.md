---
schemaVersion: 1
contentModel: systemCriterion
contentModelVersion: 1

criterion:
  code: WEB-24
  slug: web-24
  title: 별도의 업로드 경로 사용 및 권한 설정
  severity:
    level: medium
    sourceLabel: 중

classification:
  domainIdentifier: web-service
  categoryIdentifier: web-service-security-configuration

targetScope: nonExhaustive
targetIdentifiers:
  - linux
sourceTargetText: "Apache, Tomcat, Nginx, IIS, JEUS, WebtoB"

provenance:
  sourceDocumentIdentifier: kisa-cce-criteria-2026
  sourcePageRanges:
    - physicalPageStart: 343
      physicalPageEnd: 346
      printedPageStart: "343"
      printedPageEnd: "346"

sourceAnnotations:
  - annotationIdentifier: web-24-source-001
    annotationType: sourceInconsistency
    targetType: astNode
    targetReference: "web-24:remediation.linux.step:6"
    sourceLocation:
      physicalPage: 344
      printedPage: "344"
      pageRegionIdentifier: p344-web-24
    sourceText: "allowLinking"
    explanation: "절차 설명은 server.xml의 Context 요소와 allowLinking 옵션을 지칭하지만, 명령은 context.xml을 열고 예시는 servlet 요소를 제시한다."
    disposition: unresolved
    reviewStatus: pending
    verificationEvidence:
      - "PDF physical page 344의 Tomcat Step 1 설명, 명령, 설정 예시를 대조했다."
    reviewedBy: null
    reviewedAt: null
    approvedBy: null
    approvedAt: null
  - annotationIdentifier: web-24-source-002
    annotationType: sourceDuplication
    targetType: astNode
    targetReference: "web-24:remediation.linux.step:16"
    sourceLocation:
      physicalPage: 345
      printedPage: "345"
      pageRegionIdentifier: p345-web-24
    sourceText: "업로드 디렉터리 확인"
    explanation: "IIS 절차에서 Step 1 번호가 연속으로 두 번 사용된다."
    disposition: unresolved
    reviewStatus: pending
    verificationEvidence:
      - "PDF physical page 345의 IIS 단계 번호를 확인했다."
    reviewedBy: null
    reviewedAt: null
    approvedBy: null
    approvedAt: null
  - annotationIdentifier: web-24-source-003
    annotationType: sourceInconsistency
    targetType: astNode
    targetReference: "web-24:remediation.linux.command:16"
    sourceLocation:
      physicalPage: 346
      printedPage: "346"
      pageRegionIdentifier: p346-web-24
    sourceText: "# chmod 750 # ls –al"
    explanation: "chmod 명령의 대상 위치에 ls 명령이 이어져 있어 원문 기술 리터럴을 그대로 보존했다."
    disposition: unresolved
    reviewStatus: pending
    verificationEvidence:
      - "PDF physical page 346의 JEUS Step 3 명령을 확인했다."
    reviewedBy: null
    reviewedAt: null
    approvedBy: null
    approvedAt: null
  - annotationIdentifier: web-24-source-004
    annotationType: sourceInconsistency
    targetType: astNode
    targetReference: "web-24:remediation.linux.command:19"
    sourceLocation:
      physicalPage: 346
      printedPage: "346"
      pageRegionIdentifier: p346-web-24
    sourceText: "# chmod 750 # ls –al"
    explanation: "chmod 명령의 대상 위치에 ls 명령이 이어져 있어 원문 기술 리터럴을 그대로 보존했다."
    disposition: unresolved
    reviewStatus: pending
    verificationEvidence:
      - "PDF physical page 346의 WebtoB Step 3 명령을 확인했다."
    reviewedBy: null
    reviewedAt: null
    approvedBy: null
    approvedAt: null
---

## 개요

### 점검 내용

웹 서비스 제공 시 이용되는 파일 전송의 업로드 경로를 별도의 디렉터리 사용 및 적절한 권한 설정 여부 점검

### 점검 목적

웹 서버 루트 디렉터리 내 업로드 경로가 아닌 별도의 디렉터리에서 파일을 업로드할 수 있도록 하여 루트 디렉터리 내 악의적인 파일 업로드 및 실행을 방지하기 위함

### 보안 위협

웹 서버 내 별도의 파일 업로드 경로 사용 및 적절한 권한 설정을 하지 않을 경우, 악의적인 목적을 가진 파일을 업로드하여 시스템 침투, 중요 정보 유출 및 변조 등의 침해사고의 가능성이 있음

### 참고

> **참고**
>
> -

## 점검 대상 및 판단 기준

### 대상

Apache, Tomcat, Nginx, IIS, JEUS, WebtoB

### 판단 기준

- **양호:** 별도의 업로드 경로를 사용하고 일반 사용자의 접근 권한이 부여되지 않은 경우
- **취약:** 별도의 업로드 경로를 사용하지 않거나, 일반 사용자의 접근 권한이 부여된 경우

### 조치 방법

기본 경로가 아닌 별도의 업로드 경로를 지정하고, 해당 경로에 대한 일반 사용자의 접근 권한을 제한하도록 설정

### 조치 시 영향

일반적인 경우 영향 없음

## 점검 및 조치 사례

### LINUX

**Apache**

1. `apache2.conf` 파일 내 업로드 경로 및 웹서비스 디렉터리 경로 확인

   ```text command
   # vi /[Apache 설치 디렉터리]/apache2/apache2.conf(또는 apache2.conf)
   ```

   ```apache configuration
   <Directory /var/www/html/uploads>
       Options None
       AllowOverride None
       Require all denied
   </Directory>
   ```

2. 별도 업로드 경로 생성

   ```text command
   # mkdir [웹서비스 디렉터리 외 경로]
   # mkdir /var/www/html/uploads
   ```

3. 파일 실행 권한 확인

   ```text command
   # ls -al /[Apache 업로드 디렉터리]
   ```

4. 업로드 디렉터리 권한 설정

   ```text command
   # chmod 750 /var/www/html/uploads/
   # chown www-data:www-data /var/www/html/uploads/
   ```

5. `apache2.conf` 파일 내 업로드 디렉터리 접근제한 설정

   ```text command
   # vi /[Apache 설치 디렉터리]/apache2/apache2.conf
   ```

   ```apache configuration
   <Directory "/var/www/html/uploads/">
       Require all denied
   </Directory>
   ```

**Tomcat**

1. `server.xml` 파일 내 `Context` 요소 `allowLinking` 옵션 설정 (기본값 : 업로드 디렉터리 경로 존재하지 않음)

   ```text command
   # vi /[Tomcat 설치 디렉터리]/conf/context.xml
   ```

   ```xml configuration
   <servlet>
       <servlet-name>fileUploadServlet</servlet-name>
       <servlet-class>com.example.FileUploadServlet</servlet-class>
   </servlet>
   ```

2. 별도의 업로드 경로 생성

   ```text command
   # mkdir [웹서비스 디렉터리 외 경로]
   # mkdir /var/www/html/uploads
   ```

3. 업로드 디렉터리 권한 설정

   ```text command
   chmod 750 /var/www/html/uploads/
   chown tomcat:tomcat /var/www/html/uploads/
   ```

4. 지정한 디렉터리 권한을 웹 서비스에서 사용

**Nginx**

1. `nginx.conf` 파일 내 업로드 경로 확인 및 웹서비스 디렉터리 경로 사용 여부 확인

   ```text command
   #vi /[Nginx 설치 디렉터리]/conf/nginx.conf
   ```

2. 별도의 업로드 경로 생성

   ```text command
   mkdir [웹서비스 디렉터리 외 경로]
   mkdir /var/www/html/uploads
   ```

3. 업로드 디렉터리의 권한 설정

   ```text command
   chmod 750 /var/www/html/uploads/
   chown www-data:www-data /var/www/html/uploads/
   ```

4. `nginx.conf` 파일 내 업로드 디렉터리 접근제한 설정

   ```text command
   #vi /[Nginx 설치 디렉터리]/conf/nginx.conf
   ```

   ```nginx configuration
   location /uploads/ {
       alias /var/www/html/uploads/;
       autoindex on;
   }
   ```

5. 변경된 설정 내용을 적용하기 위하여 Nginx 데몬 재구동

   ```text command
   #systemctl restart nginx
   ```

**IIS**

1. 업로드 디렉터리 경로 확인

   ```text literal
   제어판 > 관리 도구 > 인터넷 정보 서비스(IIS) 관리자 > 해당 웹사이트 > 기본 설정 > ‘실제 경로’에서 홈 디렉터리 위치 확인
   ```

2. 실제 경로에 입력된 홈 디렉터리로 업로드 디렉터리 확인

   ```text literal
   [ 홈 디렉터리 위치 확인 ]
   ```

3. 웹 서비스 외부에 업로드 디렉터리를 생성

   ```text literal
   [외부 업로드 경로] > 새 폴더 생성 및 이름 지정
   ```

4. 새로 생성한 폴더에 대한 권한 설정

   ```text literal
   [외부 업로드 파일] > 속성 > 보안 > 편집 > [IIS 구동 계정 그룹] 추가 및 쓰기 권한 부여 설정
   ```

**JEUS**

1. `web.xml` 파일 내 파일 업로드 경로 확인

   ```text command
   # vi /[JEUS 설치 디렉터리]/conf/web.xml(또는 webcommon.xml)
   ```

   ```xml configuration
   <context-param>
       <param-name>uploadDir</param-name>
       <param-value>/path/to/your/upload/directory</param-value>
   </context-param>
   ```

2. 파일 업로드 경로 권한 확인

   ```text command
   # ls –al /[JEUS 업로드 디렉터리]
   ```

3. 업로드 디렉터리 권한 설정

   ```text command
   # chmod 750 # ls –al /[JEUS 업로드 디렉터리]
   # chown jeus:jeus /[JEUS 업로드 디렉터리]
   ```

**WebtoB**

1. `http.m` 파일 내 파일 업로드 경로 확인

   ```text command
   # cat /root/webtob/config/http.m
   ```

   ```text configuration
   *ALIAS
   alias_upload   URI = "/upload/", RealPath = "/home/tmax/webtob/uploads/"
   ```

2. 파일 업로드 경로 권한 확인

   ```text command
   # ls –al /[WebtoB 업로드 디렉터리]
   ```

3. 업로드 디렉터리의 권한 설정

   ```text command
   # chmod 750 # ls –al /[WebtoB 업로드 디렉터리]
   # chown tmax:tmax /[WebtoB 업로드 디렉터리]
   ```
