// 모달 관련 요소 참조함
const modalBackdrop = document.getElementById("modalBackdrop");
const modalCloseButton = modalBackdrop.querySelector(".modal-close");
const btnCancelModal = document.getElementById("btnCancelModal");
const btnUpload = document.getElementById("btnUpload");
const btnExport = document.getElementById("btnExport");
const btnSubmitUpload = document.getElementById("btnSubmitUpload");
const fileInput = document.getElementById("fileInput");
const fileNameLabel = document.getElementById("fileName");
const dryRunCheckbox = document.getElementById("dryRunCheckbox");
const csvResultSection = document.getElementById("csv-result");
const toastContainer = document.getElementById("toastContainer");

// 모달 열기 함수임
function openModal() {
  modalBackdrop.classList.add("active");
}

// 모달 닫기 함수임
function closeModal() {
  modalBackdrop.classList.remove("active");
  fileInput.value = "";
  fileNameLabel.textContent = "";
  btnSubmitUpload.disabled = true;
}

// 토스트 메시지 생성 함수임
function showToast(message, type) {
  const toast = document.createElement("div");
  toast.classList.add("toast");
  if (type === "success") {
    toast.classList.add("toast-success");
  } else if (type === "error") {
    toast.classList.add("toast-error");
  }

  const msgSpan = document.createElement("div");
  msgSpan.classList.add("toast-message");
  msgSpan.textContent = message;

  const closeBtn = document.createElement("button");
  closeBtn.classList.add("btn-text");
  closeBtn.type = "button";
  closeBtn.textContent = "닫기";
  closeBtn.onclick = () => toast.remove();

  toast.appendChild(msgSpan);
  toast.appendChild(closeBtn);

  toastContainer.appendChild(toast);

  // 자동 제거 타이머 설정함
  setTimeout(() => {
    toast.remove();
  }, 3500);
}

// 드라이런 결과 렌더링 함수임
function renderDryRunResult(response) {
  csvResultSection.innerHTML = "";

  if (!response || !response.summary) {
    return;
  }

  const card = document.createElement("div");
  card.classList.add("result-card");

  const header = document.createElement("div");
  header.classList.add("result-header");

  const title = document.createElement("div");
  title.classList.add("result-title");
  title.textContent = "CSV 검증 결과";

  const chips = document.createElement("div");
  const dryRunChip = document.createElement("span");
  dryRunChip.classList.add("chip");
  dryRunChip.textContent = response.dryRun ? "드라이런 모드" : "실제 반영";

  const errorBadge = document.createElement("span");
  errorBadge.classList.add("error-badge");
  errorBadge.textContent = "오류 " + response.summary.errorCount + "건";

  chips.appendChild(dryRunChip);
  chips.appendChild(errorBadge);

  header.appendChild(title);
  header.appendChild(chips);

  const summary = document.createElement("div");
  summary.classList.add("result-summary");
  summary.textContent =
    "총 " +
    response.summary.total +
    "건 중 성공 " +
    response.summary.successCount +
    "건, 오류 " +
    response.summary.errorCount +
    "건";

  const note = document.createElement("div");
  note.classList.add("result-note");
  note.textContent =
    "오류 행을 확인한 후 CSV 파일을 수정하여 다시 업로드하면 됨.";

  card.appendChild(header);
  card.appendChild(summary);
  card.appendChild(note);

  // 오류 테이블 생성함
  if (response.errors && response.errors.length > 0) {
    const table = document.createElement("table");
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    ["행 번호", "오류 유형", "오류 메시지", "원본 데이터 요약"].forEach(
      function (text) {
        const th = document.createElement("th");
        th.textContent = text;
        headRow.appendChild(th);
      }
    );
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");

    response.errors.forEach(function (err) {
      const tr = document.createElement("tr");
      tr.classList.add("error-row");

      const tdRow = document.createElement("td");
      tdRow.textContent = err.rowNumber;

      const tdCode = document.createElement("td");
      tdCode.textContent = err.code;

      const tdMsg = document.createElement("td");
      tdMsg.textContent = err.message;

      const tdRaw = document.createElement("td");
      const raw = err.raw || {};
      const summaryParts = [];
      if (raw.name) summaryParts.push("상품명=" + raw.name);
      if (raw.inventory !== undefined) {
        summaryParts.push("재고=" + raw.inventory);
      }
      if (raw.categoryId !== undefined) {
        summaryParts.push("카테고리ID=" + raw.categoryId);
      }
      tdRaw.textContent = summaryParts.join(", ");

      tr.appendChild(tdRow);
      tr.appendChild(tdCode);
      tr.appendChild(tdMsg);
      tr.appendChild(tdRaw);

      tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    card.appendChild(table);
  }

  csvResultSection.appendChild(card);
}

// 모의 업로드 요청 처리 함수임 (실제 서버 대신 사용함)
function simulateUpload(file, dryRun) {
  // 실제 구현에서는 FormData 생성 후 fetch 호출해야 함
  // 여기서는 데모를 위해 고정된 응답 반환함
  showToast("CSV 업로드 처리 중...", "success");

  setTimeout(function () {
    // 예시 응답 데이터임
    const mockResponse = {
      success: true,
      dryRun: dryRun,
      summary: {
        total: 120,
        successCount: 110,
        errorCount: 10
      },
      errors: [
        {
          rowNumber: 5,
          code: "MISSING_INVENTORY",
          message: "inventory 값이 비어 있음.",
          raw: {
            name: "예시상품-1",
            inventory: "",
            categoryId: "3"
          }
        },
        {
          rowNumber: 8,
          code: "INVALID_CATEGORY",
          message: "존재하지 않는 카테고리 ID 임.",
          raw: {
            name: "예시상품-2",
            inventory: "10",
            categoryId: "999"
          }
        }
      ]
    };

    if (dryRun) {
      showToast("드라이런 완료: 성공 110건, 오류 10건", "success");
      renderDryRunResult(mockResponse);
    } else {
      showToast("업로드 완료: 실제 데이터가 반영되었다고 가정함.", "success");
      csvResultSection.innerHTML = "";
    }
  }, 1000);
}

// CSV 내보내기 버튼 클릭 핸들러임
btnExport.addEventListener("click", function () {
  // 실제 구현에서는 현재 검색어, 카테고리 기준으로 다운로드 요청해야 함
  // 여기서는 단순 토스트만 보여줌
  showToast("CSV 내보내기 요청이 발생했다고 가정함.", "success");
});

// CSV 업로드 버튼 클릭 시 모달 열기함
btnUpload.addEventListener("click", openModal);

// 모달 닫기 버튼 핸들러임
modalCloseButton.addEventListener("click", closeModal);
btnCancelModal.addEventListener("click", closeModal);

// 배경 클릭 시 모달 닫기 처리함
modalBackdrop.addEventListener("click", function (event) {
  if (event.target === modalBackdrop) {
    closeModal();
  }
});

// 파일 선택 변경 시 파일명 표시 및 업로드 버튼 활성화 상태 갱신함
fileInput.addEventListener("change", function () {
  const file = fileInput.files[0];
  if (file) {
    fileNameLabel.textContent = file.name;
    btnSubmitUpload.disabled = false;
  } else {
    fileNameLabel.textContent = "";
    btnSubmitUpload.disabled = true;
  }
});

// 업로드 버튼 클릭 시 모의 업로드 실행함
btnSubmitUpload.addEventListener("click", function () {
  const file = fileInput.files[0];
  if (!file) {
    showToast("CSV 파일을 먼저 선택해야 함.", "error");
    return;
  }
  const dryRun = dryRunCheckbox.checked;

  closeModal();
  simulateUpload(file, dryRun);
});
