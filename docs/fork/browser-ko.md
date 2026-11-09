# Windows에서 개조 OBS 브라우저 소스 사용하기

## 포터블 빌드

현재 개발 중인 PR 브랜치를 PowerShell에서 내려받는다. 병합 후에는 `--branch setup/use-huihuing-obs-browser`를 생략할 수 있다. 이 소스의 Windows 빌드 프리셋은 Visual Studio 2026의 C++ 데스크톱 개발 도구, Windows SDK 10.0.26100.0, Visual Studio 18 2026 생성기를 지원하는 CMake를 사용한다.

```powershell
git clone --recursive --branch setup/use-huihuing-obs-browser https://github.com/Huihuing/obs-studio.git obs-browser-fork
cd obs-browser-fork
.\build-aux\fork\Build-Portable.ps1
```

빌드가 끝나면 `build_x64`에 생성된 ZIP을 새 폴더에 풀고 `bin\64bit\obs64.exe`를 실행한다. 포터블 설정과 공식 자동 업데이트 비활성화 표시는 ZIP 루트에 들어 있다. 빌드에 사용한 두 저장소의 소스 주소는 ZIP 안의 `FORK-SOURCE.txt`에 기록된다.

## 소스마다 JavaScript 적용

1. 브라우저 소스의 **속성**에서 URL 또는 로컬 HTML을 지정한다.
2. **사용자 지정 CSS** 아래 **사용자 지정 JavaScript**에 코드를 입력한다.
3. **이 컴퓨터에서 이 스크립트 허용**을 누른다. 창에 표시된 주소, 코드, OBS 제어 권한을 확인하고 허용한 다음 속성 창에서 **확인**을 누른다.
4. 다음 예제를 사용하면 브라우저 소스 왼쪽 위에 초록색 배지가 나타난다. 소스를 새로고침해 배지가 다시 생기는지 확인한다.

```js
const badge = document.createElement("div");
badge.textContent = "OBS JavaScript 작동 중";
badge.style.cssText = "position:fixed;top:8px;left:8px;z-index:2147483647;padding:8px;background:#075e48;color:white";
document.body.append(badge);
```

코드는 지정한 웹 출처의 메인 페이지가 로드된 후 실행된다. 로컬 HTML은 선택한 파일 경로를 기준으로 한다. 코드, 주소, OBS 제어 권한을 바꾼 뒤에는 다시 허용한다. 스크립트를 중지하려면 입력란을 비우고 **확인**을 누른다. 장면 파일을 승인 기록이 없는 다른 PC로 가져가면 거기서 다시 승인해야 한다.

## 압축 해제한 Chrome 확장 시험

이 빌드는 시작할 때 `manifest.json`이 들어 있는 확장 디렉터리 하나를 CEF에 전달한다. 확장은 매니페스트가 지정한 주소에 접근할 수 있고 브라우저 프로필 단위로 적용된다. OBS를 완전히 종료한 뒤, 포터블 ZIP을 푼 폴더에서 실행한다.

```powershell
cd .\bin\64bit
.\obs64.exe "--obs-browser-extension=C:\OBS Extensions\my-extension"
```

공백과 한글이 들어간 절대 경로를 사용할 수 있다. 경로에 쉼표가 포함되면 로딩을 거부한다. 옵션 없이 다시 시작하면 확장이 꺼진다. 이 단계에서 확인할 수 있는 범위는 확장의 콘텐츠 스크립트, MV3 서비스 워커, 네트워크 규칙 등 각 기능의 호환성이다. 압축된 CRX 설치, 웹 스토어 설치, 툴바 팝업은 지원 범위 밖이다.

직접 시험하려면 소스 저장소의 [확장 테스트 예제](../../plugins/obs-browser)에서 `tests/extension-smoke/README.md`를 연다. 로컬 테스트 페이지에 세 결과가 각각 표시된다. 자동 빌드가 활성화된 경우 본체 Actions의 **Fork portable build and browser checks**에서 Linux CEF 테스트 로그와 Windows 빌드 결과를 확인할 수 있다.

[공식 OBS 업데이트를 포크에 반영하는 절차](upstream-ko.md)
