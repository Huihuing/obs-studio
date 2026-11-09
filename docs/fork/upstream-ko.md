# 공식 OBS 업데이트를 포크에 반영하기

개조 브라우저 기능을 두 포크의 `master`에 병합한 뒤 사용하는 절차다. OBS의 릴리스마다 본체가 지정한 브라우저 커밋이 다를 수 있다. 브라우저 변경을 먼저 병합하고, 본체의 `plugins/obs-browser`가 그 결과를 가리키게 한다.

### 1. 공식 릴리스와 두 커밋 확인

Git Bash에서 새 빈 디렉터리를 열고 실행한다. 태그 선택은 [OBS 공식 릴리스](https://github.com/obsproject/obs-studio/releases)를 기준으로 한다.

```bash
read -r -p '공식 릴리스 태그 (예 33.0.1): ' tag
git clone https://github.com/Huihuing/obs-studio.git studio
git clone https://github.com/Huihuing/obs-browser.git browser
git -C studio fetch --no-tags https://github.com/obsproject/obs-studio.git "refs/tags/$tag"
studio_target=$(git -C studio rev-parse 'FETCH_HEAD^{commit}')
old_browser=$(git -C studio rev-parse origin/master:plugins/obs-browser)
browser_target=$(git -C studio rev-parse "$studio_target:plugins/obs-browser")
git -C studio ls-tree "$studio_target" -- plugins/obs-browser
git -C studio merge-base --is-ancestor "$studio_target" origin/master && echo '이미 반영된 OBS 릴리스'
```

앞의 명령에서 오류가 나면 다음 단계로 넘어가기 전에 원인을 확인한다. `ls-tree`에는 `160000 commit`이 나와야 한다. 이미 반영된 릴리스라는 메시지가 나오면 여기서 끝난다. 포크의 시작점이 공식 개발 브랜치여서 이미 포함한 정식 릴리스가 있을 수 있다.

### 2. 브라우저 포크 갱신

```bash
git -C browser fetch --no-tags https://github.com/obsproject/obs-browser.git "$browser_target"
git -C browser merge-base --is-ancestor "$old_browser" origin/master
git -C browser merge-base --is-ancestor "$browser_target" origin/master && echo '공식 브라우저 변경이 이미 포함됨'
```

첫 번째 조상 검사가 실패하면 현재 본체에 연결된 개조 커밋을 포함하는 브라우저 브랜치부터 확인한다. 두 번째 검사에서 이미 포함됐으면 3단계로 간다. 새 브라우저 변경이 있으면 아래 브랜치에서 병합한다.

```bash
git -C browser switch -c "sync/obs-$tag" origin/master
git -C browser merge --no-ff "$browser_target"
```

충돌이 생기면 양쪽의 변경을 검토하고 `git -C browser add <해결한 파일>`, `git -C browser merge --continue`로 마무리한다. 취소할 때는 `git -C browser merge --abort`를 쓴다. 브라우저 설정과 실행 경로를 확인한 뒤 `git -C browser push -u origin HEAD`로 올리고 `Huihuing/obs-browser`의 `master`에 PR을 연다. 다음 업데이트에서도 커밋 간 조상 관계를 확인할 수 있도록 **Create a merge commit**으로 병합한다.

### 3. 본체와 브라우저 참조를 한 PR로 검증

브라우저 PR이 병합된 뒤 같은 Git Bash 세션에서 실행한다. 두 조상 검사를 모두 통과해야 새 포인터에 기존 개조 커밋과 공식 브라우저 변경이 함께 들어간다.

```bash
git -C browser fetch origin master
browser_pin=$(git -C browser rev-parse origin/master)
git -C browser merge-base --is-ancestor "$old_browser" "$browser_pin" &&
  git -C browser merge-base --is-ancestor "$browser_target" "$browser_pin" &&
  echo '기존 개조 커밋과 공식 브라우저 커밋 확인'
git -C studio switch -c "sync/obs-$tag" origin/master
git -C studio merge --no-ff --no-commit "$studio_target"
```

확인 메시지가 없으면 포인터를 변경하기 전에 브라우저 브랜치 이력을 확인한다. 본체 병합 중 `plugins/obs-browser`에서 충돌이 발생할 수 있다. 아래에서 검증한 `browser_pin`을 지정해 이 충돌을 해결한다. `.gitmodules`에 충돌이 있으면 공식 저장소의 다른 서브모듈 변경도 반영한 후 진행한다.

```bash
git -C studio config -f .gitmodules submodule.plugins/obs-browser.url https://github.com/Huihuing/obs-browser.git
git -C studio add .gitmodules
git -C studio update-index --add --cacheinfo "160000,$browser_pin,plugins/obs-browser"
git -C studio diff --name-only --diff-filter=U
git -C studio submodule sync --recursive
git -C studio submodule update --init --recursive
git -C studio rev-parse :plugins/obs-browser
git -C studio/plugins/obs-browser rev-parse HEAD
git -C studio diff --cached --check
```

충돌 파일 목록은 비어 있어야 하며 두 `rev-parse` 출력은 모두 `browser_pin`과 같아야 한다. 새 본체에서 Windows x64 빌드와 브라우저 소스 기능을 확인한 뒤 커밋하고 PR을 연다.

```bash
git -C studio commit -m "Merge OBS $tag and pin the tested browser fork"
git -C studio push -u origin HEAD
```

PR의 대상은 `Huihuing/obs-studio:master`다. 본체도 **Create a merge commit**으로 병합해 다음 번 릴리스 검사가 이미 반영한 버전을 건너뛸 수 있게 한다.

### 자동 PR 확인

두 포크의 기본 브랜치에 변경을 병합한 뒤 GitHub Actions를 활성화한다. 각 저장소의 **Settings → Actions → General → Workflow permissions**에서 **Allow GitHub Actions to create and approve pull requests**가 켜져 있어야 초안 PR을 열 수 있다.

브라우저 워크플로는 매일 한국 시간 15시 17분에 공식 최신 정식 릴리스의 브라우저 커밋을 확인한다. 본체는 15시 37분에 같은 릴리스를 확인한다. 공식 변경이 이미 포함돼 있으면 종료한다. 브라우저 변경이 있으면 그 포크에 초안 PR을 열고, 병합된 뒤 다음 본체 검사에서 확정된 브라우저 커밋을 연결한 초안 PR을 연다. 두 워크플로 모두 Actions 화면에서 직접 실행할 수도 있다.

자동 처리가 가능한 충돌은 검증한 브라우저 커밋 포인터로 한정한다. 다른 파일이 충돌하면 해당 실행 로그에 경로가 표시된다. 위 절차로 수정한 뒤 병합한다. 봇으로 연 PR은 GitHub 설정에 따라 워크플로 실행 승인 또는 별도 수동 검증이 필요하다. 두 저장소를 각각 자신의 토큰으로 갱신하므로 다른 저장소의 쓰기 토큰을 등록할 필요가 없다.
