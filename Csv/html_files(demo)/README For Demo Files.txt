파일경로: ./stock_csv_demo.html
파일명: stock_csv_demo.html

역할:
- CSV 내보내기 버튼
- CSV 업로드 모달
- 드라이런 결과 요약 + 오류 테이블 표시
- 실제 백엔드 대신 모의 응답(mock) 으로 동작 시연

이 상태에서:

1. stock_csv_demo.html 파일로 저장하고
2. 더블 클릭해서 브라우저로 열면
- CSV 내보내기 버튼은 토스트만 띄우고
- CSV 업로드 버튼은 모달 열리고
- 파일 선택 후 업로드 누르면 드라이런 결과 카드가 아래에 생기는 구조

---------------------------------------------------------------------------------------------------

위의 html 파일을 CSS/JS로 분리.

< CSS >
파일 경로: ./stock_csv_demo.css
파일명: stock_csv_demo.css
역할: 기존 stock_csv_demo.html 안 <style> ... </style> 내용 전부 분리



---

< JS >
파일 경로: ./stock_csv_demo.js
파일명: stock_csv_demo.js

역할:

- 기존 stock_csv_demo.html 안에 있던 <script> ... </script> 전체를 외부 파일로 분리한 버전
- HTML에서는 나중에 <script src="stock_csv_demo.js"></script> 한 줄만 추가해서 사용하면 됨
- 위치는 예전처럼 </body> 바로 위에 두면 됨

