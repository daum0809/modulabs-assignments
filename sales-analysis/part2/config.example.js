/**
 * [담당2] Supabase 접속 정보
 *
 * 이 파일을 복사해서 config.js로 이름을 바꾸고 값을 채우세요.
 *   - url : Supabase 대시보드 > Project Settings > Data API > Project URL (끝의 /rest/v1/ 은 빼기)
 *   - key : Project Settings > API Keys > Publishable key (sb_publishable_...)
 *
 * publishable 키는 브라우저에 공개되는 용도의 키예요. 데이터는 DB의 RLS 정책이 지켜요.
 * secret / service_role 키는 절대 여기에 넣지 마세요.
 */
window.SUPABASE_CONFIG = {
  url: "https://xxxxxxxx.supabase.co",
  key: "sb_publishable_xxxxxxxx",
  // 토스페이먼츠 개발자센터 > API 개별 연동 키 > 클라이언트 키 (test_ck_...). 시크릿 키(test_sk_)는 넣지 않기
  tossClientKey: "test_ck_xxxxxxxx",
};
