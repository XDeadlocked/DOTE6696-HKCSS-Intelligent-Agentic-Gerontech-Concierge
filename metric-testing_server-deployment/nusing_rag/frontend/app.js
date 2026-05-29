(function () {
  const DEFAULT_HOST = "http://127.0.0.1:8000";
  const WELCOME_TEXT = "您好，歡迎使用長者輔具推薦服務！請選擇您需要的服務項目。";
  const isFileProtocol = window.location.protocol === "file:";
  const originBase = isFileProtocol ? DEFAULT_HOST : window.location.origin;
  const apiBase = originBase + "/api/v1";
  const wsBase = (originBase.startsWith("https://") ? "wss://" : "ws://") + originBase.replace(/^https?:\/\//, "");

  const state = {
    sessionId: null,
    currentFlow: "idle",
    messages: [],
    step: null,
    composer: null,
    categories: [],
    productView: null,
    recommendations: [],
    inventoryResults: [],
    productDetail: null,
    selectedCategory: null,
    assessmentSocket: null,
    nursingSocket: null,
    activeDeviceTag: null,
    activeFollowupAnswer: null,
    pendingFlowAfterSocket: null,
    multiSelectOptions: [],
    selectedMultiOptions: [],
    thinkingMessageId: null,
    isBusy: false,
    error: null,
    typingTimer: null,
  };

  const elements = {
    errorBanner: document.getElementById("errorBanner"),
    busyBanner: document.getElementById("busyBanner"),
    chatPanel: document.getElementById("chatPanel"),
    stepTitle: document.getElementById("stepTitle"),
    stepHint: document.getElementById("stepHint"),
    actionPanel: document.getElementById("actionPanel"),
    composerForm: document.getElementById("composerForm"),
    composerLabel: document.getElementById("composerLabel"),
    composerInput: document.getElementById("composerInput"),
    composerSubmit: document.getElementById("composerSubmit"),
    composerHint: document.getElementById("composerHint"),
    restartButton: document.getElementById("restartButton"),
    drawer: document.getElementById("productDrawer"),
    drawerCategory: document.getElementById("drawerCategory"),
    drawerTitle: document.getElementById("drawerTitle"),
    drawerPrice: document.getElementById("drawerPrice"),
    drawerStock: document.getElementById("drawerStock"),
    drawerDimensions: document.getElementById("drawerDimensions"),
    drawerDescription: document.getElementById("drawerDescription"),
  };

  function makeId() {
    return String(Date.now()) + "-" + Math.random().toString(36).slice(2, 9);
  }

  function escapeHtml(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function escapeAttr(text) {
    return escapeHtml(text);
  }

  function markdownToHtml(md) {
    var text = String(md == null ? "" : md);
    text = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    var paragraphs = text.split(/\n\n+/);
    var result = [];
    var i, j, p, lines;
    for (i = 0; i < paragraphs.length; i++) {
      p = paragraphs[i].trim();
      if (!p) continue;
      if (/^\*\*\*+$/.test(p) || /^---+$/.test(p)) continue;
      lines = p.split("\n");
      if (lines.length > 1 && /^[\-\*]\s/.test(lines[0]) && /^[\-\*]\s/.test(lines[lines.length - 1])) {
        var items = [];
        for (j = 0; j < lines.length; j++) {
          if (/^[\-\*]\s/.test(lines[j])) {
            items.push("<li>" + inlineMarkdown(lines[j].replace(/^[\-\*]\s+/, "")) + "</li>");
          }
        }
        result.push("<ul>" + items.join("") + "</ul>");
      } else if (lines.length > 1 && /^\d+[\.\、]\s/.test(lines[0]) && /^\d+[\.\、]\s/.test(lines[lines.length - 1])) {
        var olItems = [];
        for (j = 0; j < lines.length; j++) {
          if (/^\d+[\.\、]\s/.test(lines[j])) {
            olItems.push("<li>" + inlineMarkdown(lines[j].replace(/^\d+[\.\、]\s+/, "")) + "</li>");
          }
        }
        result.push("<ol>" + olItems.join("") + "</ol>");
      } else if (lines.length === 1 && /^[\-\*]\s/.test(lines[0])) {
        result.push("<ul><li>" + inlineMarkdown(lines[0].replace(/^[\-\*]\s+/, "")) + "</li></ul>");
      } else {
        var joined = [];
        for (j = 0; j < lines.length; j++) {
          joined.push(inlineMarkdown(lines[j]));
        }
        result.push("<p>" + joined.join("<br />") + "</p>");
      }
    }
    return result.join("");
  }

  function inlineMarkdown(text) {
    return text
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");
  }

  function nowIso() {
    return new Date().toISOString();
  }

  function formatTime(isoText) {
    if (!isoText) {
      return "--:--";
    }
    const date = new Date(isoText);
    if (Number.isNaN(date.getTime())) {
      return "--:--";
    }
    return date.toLocaleTimeString("zh-HK", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  }

  function createMessage(role, content, extra) {
    const normalizedContent = String(content == null ? "" : content);
    return Object.assign(
      {
        id: makeId(),
        role: role,
        kind: "text",
        content: normalizedContent,
        displayContent: normalizedContent,
        references: [],
        safetyNotice: "",
        isStreaming: false,
        createdAt: nowIso(),
        completedAt: null,
      },
      extra || {},
    );
  }

  function setError(message) {
    state.error = message || null;
    if (state.error) {
      elements.errorBanner.textContent = state.error;
      elements.errorBanner.classList.remove("hidden");
    } else {
      elements.errorBanner.classList.add("hidden");
      elements.errorBanner.textContent = "";
    }
  }

  function setBusy(busy) {
    state.isBusy = Boolean(busy);
    elements.composerInput.disabled = state.isBusy;
    elements.composerSubmit.disabled = state.isBusy;
    elements.restartButton.disabled = state.isBusy;
    if (state.isBusy) {
      elements.busyBanner.classList.remove("hidden");
    } else {
      elements.busyBanner.classList.add("hidden");
    }
  }

  function renderHeader() {
  }

  function appendMessage(role, content, extra) {
    state.messages.push(createMessage(role, content, extra));
    renderMessages();
  }

  function showThinkingMessage() {
    if (state.thinkingMessageId) return;
    var msgId = makeId();
    state.thinkingMessageId = msgId;
    state.messages.push({
      id: msgId,
      role: "assistant",
      kind: "thinking",
      content: "",
      displayContent: "",
      references: [],
      safetyNotice: "",
      isStreaming: false,
      createdAt: nowIso(),
      completedAt: null,
    });
    renderMessages();
  }

  function hideThinkingMessage() {
    if (!state.thinkingMessageId) return;
    state.messages = state.messages.filter(function (m) {
      return m.id !== state.thinkingMessageId;
    });
    state.thinkingMessageId = null;
    renderMessages();
  }

  function stopTypingLoop() {
    if (state.typingTimer) {
      window.clearInterval(state.typingTimer);
      state.typingTimer = null;
    }
  }

  function ensureTypingLoop() {
    if (state.typingTimer) {
      return;
    }
    state.typingTimer = window.setInterval(function () {
      let changed = false;
      let hasPendingTyping = false;

      state.messages.forEach(function (message) {
        const fullText = String(message.content || "");
        const shownText = String(message.displayContent || "");
        if (shownText.length < fullText.length) {
          const remaining = fullText.length - shownText.length;
          const step = remaining > 30 ? 3 : remaining > 10 ? 2 : 1;
          message.displayContent = fullText.slice(0, shownText.length + step);
          changed = true;
        }
        if (message.isStreaming || String(message.displayContent || "").length < fullText.length) {
          hasPendingTyping = true;
        }
      });

      if (changed) {
        renderMessages();
      }
      if (!hasPendingTyping) {
        stopTypingLoop();
      }
    }, 24);
  }

  function appendStreamingChunk(chunk) {
    const chunkText = String(chunk == null ? "" : chunk);
    if (!chunkText) {
      return;
    }
    const last = state.messages[state.messages.length - 1];
    if (last && last.role === "assistant" && last.isStreaming) {
      last.content += chunkText;
    } else {
      state.messages.push(
        createMessage("assistant", "", {
          displayContent: "",
          isStreaming: true,
        }),
      );
      state.messages[state.messages.length - 1].content += chunkText;
    }
    ensureTypingLoop();
    renderMessages();
  }

  function finalizeStreamingMessage(meta) {
    const last = state.messages[state.messages.length - 1];
    if (!last || !last.isStreaming) {
      return;
    }
    last.isStreaming = false;
    last.references = meta && Array.isArray(meta.references) ? meta.references : [];
    last.safetyNotice = meta && meta.safetyNotice ? meta.safetyNotice : "";
    last.completedAt = nowIso();
    last.displayContent = last.content;
    stopTypingLoop();
    renderMessages();
  }

  function renderEmptyState() {
    return "";
  }

  function renderNoResultCard(title, description) {
    return (
      '<div class="no-result-card"><h3>' +
      escapeHtml(title) +
      "</h3><p>" +
      escapeHtml(description) +
      "</p></div>"
    );
  }

  function renderStructuredCards(message) {
    if (message.kind === "recommendations") {
      if (!message.items || !message.items.length) {
        return renderNoResultCard("目前還沒有推薦方向", "您可以返回主選單，或重新進行問題解決型推薦。");
      }
      return (
        '<div class="card-list">' +
        (message.items || [])
          .map(function (item) {
            return (
              '<div class="summary-card">' +
              "<h3>" +
              escapeHtml(item.content || item.device_tag || "推薦") +
              "</h3>" +
              '<div class="summary-meta">device_tag: ' +
              escapeHtml(item.device_tag || "-") +
              (item.category_id ? "<br />category_id: " + escapeHtml(item.category_id) : "") +
              "</div></div>"
            );
          })
          .join("") +
        "</div>"
      );
    }

    if (message.kind === "inventory") {
      if (!message.items || !message.items.length) {
        return renderNoResultCard("暫時找不到合適商品", "建議改用其他關鍵字、重新選設備方向，或先瀏覽產品分類。");
      }
      return (
        '<div class="card-list">' +
        (message.items || [])
          .map(function (item) {
            return (
              '<div class="inventory-card">' +
              "<h3>" +
              escapeHtml(item.product_name || "未命名商品") +
              "</h3>" +
              '<div class="inventory-meta">分類：' +
              escapeHtml(item.category_name || "-") +
              "<br />庫存：" +
              escapeHtml(item.stock_status || "-") +
              "<br />分數：" +
              escapeHtml(item.score == null ? "-" : Number(item.score).toFixed(3)) +
              "</div></div>"
            );
          })
          .join("") +
        "</div>"
      );
    }

    return "";
  }

  function renderMessages() {
    elements.chatPanel.innerHTML =
      renderEmptyState() +
      state.messages
        .map(function (message, index) {
          if (message.kind === "thinking") {
            return (
              '<div class="message-row assistant">' +
              '<div class="bubble assistant thinking-bubble">' +
              '<div class="thinking-indicator">' +
              '<span class="thinking-text">正在思考中</span>' +
              '<span class="thinking-dots">' +
              '<span class="thinking-dot-bounce"></span>' +
              '<span class="thinking-dot-bounce"></span>' +
              '<span class="thinking-dot-bounce"></span>' +
              '</span>' +
              '</div>' +
              '</div></div>'
            );
          }
          const meta = [];
          if (message.references && message.references.length) {
            meta.push("參考來源：" + message.references.join("、"));
          }
          if (message.safetyNotice) {
            meta.push(message.safetyNotice);
          }
          const visibleContent =
            message.displayContent || (message.isStreaming ? "正在整理回答" : message.content || "");
          const messageTime = formatTime(message.completedAt || message.createdAt);
          const isWelcomeMessage = index === 0 && message.role === "assistant" && message.content === WELCOME_TEXT;
          return (
            '<div class="message-row ' +
            escapeAttr(message.role) +
            '">' +
            '<div class="bubble ' +
            escapeAttr(message.role) +
            (message.isStreaming ? " is-streaming" : "") +
            '">' +
            '<div class="message-role">' +
            (message.role === "user" ? "您" : "系統助手") +
            "</div>" +
            (isWelcomeMessage ? '<div class="welcome-image-wrapper"><img src="./assessment-q-common@2x.png" class="welcome-image" alt="形象照" /></div>' : "") +
            '<div class="message-content">' +
            (message.role === "user" ? escapeHtml(visibleContent) : markdownToHtml(visibleContent)) +
            (message.isStreaming ? '<span class="streaming-caret">|</span>' : "") +
            "</div>" +
            renderStructuredCards(message) +
            (meta.length ? '<div class="message-meta">' + escapeHtml(meta.join("\n")) + "</div>" : "") +
            '<div class="message-foot"><span class="message-time">' +
            escapeHtml(messageTime) +
            "</span>" +
            (message.isStreaming
              ? '<span class="message-status">正在輸入<span class="streaming-indicator"><span class="streaming-dot"></span><span class="streaming-dot"></span><span class="streaming-dot"></span></span></span>'
              : "") +
            "</div>" +
            "</div></div>"
          );
        })
        .join("");
    elements.chatPanel.scrollTop = elements.chatPanel.scrollHeight;
  }

  function setStep(step, composer) {
    state.step = step || {
      kind: "idle",
      title: "請稍候",
      hint: "系統正在準備下一步。",
    };
    state.composer = composer || null;
    renderStep();
    renderComposer();
    renderHeader();
  }

  function renderStep() {
    const step = state.step || {};
    elements.stepTitle.textContent = step.title || "請稍候";
    elements.stepHint.textContent = step.hint || "";

    if (!step.kind || step.kind === "idle") {
      elements.actionPanel.innerHTML = '<div class="note-box">當前沒有可操作項目，請稍候。</div>';
      return;
    }

    if (step.kind === "menu") {
      elements.actionPanel.innerHTML =
        '<div class="options-grid">' +
        (step.options || [])
          .map(function (option) {
            return (
              '<button class="option-button" data-main-service="' +
              escapeAttr(option.value) +
              '">' +
              '<span class="option-title">' +
              escapeHtml(option.title) +
              '</span><span class="option-desc">' +
              escapeHtml(option.description) +
              "</span></button>"
            );
          })
          .join("") +
        "</div>";
      return;
    }

    if (step.kind === "assessment-question") {
      if (step.nodeType === "multi_choice") {
        state.multiSelectOptions = step.options || [];
        state.selectedMultiOptions = [];
        elements.actionPanel.innerHTML =
          '<div class="checkbox-grid">' +
          (step.options || [])
            .map(function (option, index) {
              return (
                '<label class="checkbox-option" data-index="' + index + '">' +
                '<input type="checkbox" class="multi-checkbox" value="' + escapeAttr(option) + '" />' +
                '<span class="checkbox-label-text">' + escapeHtml(option) + '</span>' +
                '</label>'
              );
            })
            .join("") +
          "</div>" +
          '<div class="action-row multi-actions">' +
          '<button class="secondary-button" data-multi-reset="true">清空重選</button>' +
          '<button class="primary-button" data-multi-confirm="true" disabled>確認選擇</button>' +
          "</div>";
        return;
      }
      elements.actionPanel.innerHTML =
        '<div class="options-grid">' +
        (step.options || [])
          .map(function (option) {
            return (
              '<button class="option-button" data-assessment-option="' +
              escapeAttr(option) +
              '">' +
              '<span class="option-title">' +
              escapeHtml(option) +
              "</span></button>"
            );
          })
          .join("") +
        "</div>";
      return;
    }

    if (step.kind === "recommendations") {
      if (!step.items || !step.items.length) {
        elements.actionPanel.innerHTML =
          renderNoResultCard("目前還沒有可繼續追問的方向", "您可以返回主選單，或重新開始問題解決型推薦。") +
          '<div class="action-row"><button class="secondary-button" data-return-menu="true">返回主選單</button></div>';
        return;
      }
      elements.actionPanel.innerHTML =
        '<div class="mini-grid">' +
        (step.items || [])
          .map(function (item) {
            return (
              '<div class="summary-card">' +
              "<h3>" +
              escapeHtml(item.content || item.device_tag || "推薦方向") +
              "</h3>" +
              '<div class="summary-meta">device_tag: ' +
              escapeHtml(item.device_tag || "-") +
              '</div><button class="product-button" data-device-tag="' +
              escapeAttr(item.device_tag || "") +
              '">查看此方向的後續問題</button></div>'
            );
          })
          .join("") +
        '</div><div class="action-row"><button class="secondary-button" data-return-menu="true">返回主選單</button></div>';
      return;
    }

    if (step.kind === "followup-question") {
      elements.actionPanel.innerHTML =
        '<div class="options-grid">' +
        (step.options || [])
          .map(function (option) {
            return (
              '<button class="option-button" data-followup-option="' +
              escapeAttr(option.label || "") +
              '">' +
              '<span class="option-title">' +
              escapeHtml(option.label || "") +
              '</span><span class="option-desc">' +
              escapeHtml(option.text || "") +
              "</span></button>"
            );
          })
          .join("") +
        '</div><div class="action-row"><button class="secondary-button" data-show-composer="followup_custom">其他補充描述</button></div>';
      return;
    }

    if (step.kind === "nested-followup") {
      elements.actionPanel.innerHTML =
        '<div class="options-grid">' +
        (step.options || [])
          .map(function (option) {
            return (
              '<button class="option-button" data-nested-option="' +
              escapeAttr(option.label || "") +
              '">' +
              '<span class="option-title">' +
              escapeHtml(option.label || "") +
              '</span><span class="option-desc">' +
              escapeHtml(option.text || "") +
              "</span></button>"
            );
          })
          .join("") +
        '</div><div class="action-row"><button class="secondary-button" data-show-composer="nested_custom">其他補充描述</button></div>';
      return;
    }

    if (step.kind === "browse-categories") {
      elements.actionPanel.innerHTML =
        '<div class="options-grid">' +
        (step.categories || [])
          .map(function (category) {
            return (
              '<button class="option-button" data-category-name="' +
              escapeAttr(category.category_name || "") +
              '">' +
              '<span class="option-title">' +
              escapeHtml(category.category_name || "未命名分類") +
              '</span><span class="option-desc">商品數量：' +
              escapeHtml(String(category.product_count || 0)) +
              "</span></button>"
            );
          })
          .join("") +
        '</div><div class="action-row"><button class="secondary-button" data-show-composer="browse_search">以關鍵字搜尋</button><button class="secondary-button" data-return-menu="true">返回主選單</button></div>';
      return;
    }

    if (step.kind === "products") {
      const view = step.view || {};
      if (!view.items || !view.items.length) {
        elements.actionPanel.innerHTML =
          renderNoResultCard("暫無符合條件的產品", "您可以改用其他關鍵字、重新選分類，或返回主選單重新開始。") +
          '<div class="action-row"><button class="secondary-button" data-show-composer="browse_search">重新搜尋</button><button class="secondary-button" data-browse-categories="true">重新選分類</button><button class="secondary-button" data-return-menu="true">返回主選單</button></div>';
        return;
      }
      elements.actionPanel.innerHTML =
        '<div class="products-grid">' +
        (view.items || [])
          .map(function (product) {
            return (
              '<div class="product-card">' +
              "<h3>" +
              escapeHtml(product.product_name || "未命名商品") +
              "</h3>" +
              '<div class="product-meta">分類：' +
              escapeHtml(product.category_name || "-") +
              (product.description ? "<br />" + escapeHtml(product.description).slice(0, 72) : "") +
              '</div><button class="product-button" data-product-name="' +
              escapeAttr(product.product_name || "") +
              '">查看詳情</button></div>'
            );
          })
          .join("") +
        '</div><div class="pager-row"><span class="pager-info">第 ' +
        escapeHtml(String(view.page || 1)) +
        " / " +
        escapeHtml(String(view.totalPages || 1)) +
        ' 頁</span><div class="action-row"><button class="pager-button" data-product-page="prev"' +
        ((view.page || 1) <= 1 ? " disabled" : "") +
        '>上一頁</button><button class="pager-button" data-product-page="next"' +
        ((view.page || 1) >= (view.totalPages || 1) ? " disabled" : "") +
        '>下一頁</button><button class="secondary-button" data-show-composer="browse_search">重新搜尋</button><button class="secondary-button" data-browse-categories="true">重新選分類</button></div></div>';
      return;
    }

    if (step.kind === "inventory") {
      if (!step.items || !step.items.length) {
        elements.actionPanel.innerHTML =
          renderNoResultCard("暫時找不到合適商品", "您可以先瀏覽產品分類，或回到主選單重新描述需求。") +
          '<div class="action-row"><button class="secondary-button" data-return-menu="true">返回主選單</button><button class="secondary-button" data-browse-categories="true">瀏覽產品分類</button></div>';
        return;
      }
      elements.actionPanel.innerHTML =
        '<div class="card-list">' +
        (step.items || [])
          .map(function (item) {
            return (
              '<div class="inventory-card">' +
              "<h3>" +
              escapeHtml(item.product_name || "未命名商品") +
              "</h3>" +
              '<div class="inventory-meta">分類：' +
              escapeHtml(item.category_name || "-") +
              "<br />庫存：" +
              escapeHtml(item.stock_status || "-") +
              "<br />分數：" +
              escapeHtml(item.score == null ? "-" : Number(item.score).toFixed(3)) +
              "</div></div>"
            );
          })
          .join("") +
        '</div><div class="action-row"><button class="secondary-button" data-return-menu="true">返回主選單</button><button class="secondary-button" data-browse-categories="true">瀏覽產品分類</button></div>';
      return;
    }

    if (step.kind === "nursing-ready") {
      elements.actionPanel.innerHTML =
        '<div class="action-row"><button class="secondary-button" data-show-composer="nursing">繼續提出護理問題</button><button class="secondary-button" data-return-menu="true">返回主選單</button></div>';
      return;
    }

    elements.actionPanel.innerHTML = '<div class="note-box">請按照對話提示繼續操作。</div>';
  }

  function renderComposer() {
    const composer = state.composer;
    if (!composer) {
      elements.composerForm.classList.add("hidden");
      elements.composerInput.value = "";
      return;
    }
    elements.composerForm.classList.remove("hidden");
    elements.composerLabel.textContent = composer.label || "請輸入內容";
    elements.composerInput.placeholder = composer.placeholder || "";
    elements.composerHint.textContent = composer.hint || "";
    elements.composerSubmit.textContent = composer.submitText || "送出";
  }

  async function request(path, options) {
    const response = await fetch(apiBase + path, Object.assign({ cache: "no-store" }, options || {}));
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || "request_failed");
    }
    return response.json();
  }

  function jsonRequest(method, path, body) {
    return request(path, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  async function ensureSession(forceNew) {
    if (state.sessionId && !forceNew) {
      return state.sessionId;
    }
    const created = await jsonRequest("POST", "/sessions", {});
    state.sessionId = created.session_id;
    renderHeader();
    return state.sessionId;
  }

  async function connectAssessmentSocket() {
    const sessionId = await ensureSession();
    const socket = state.assessmentSocket;
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      return socket;
    }
    return new Promise(function (resolve) {
      const createdSocket = new WebSocket(wsBase + "/ws/assessment/" + encodeURIComponent(sessionId));
      state.assessmentSocket = createdSocket;
      createdSocket.onopen = function () {
        resolve(createdSocket);
      };
      createdSocket.onerror = function () {
        resolve(null);
      };
      createdSocket.onmessage = function (event) {
        const payload = JSON.parse(event.data);
        if (payload.type === "question") {
          presentAssessmentQuestion(payload.data || {});
          return;
        }
        if (payload.type === "completed") {
          presentRecommendations(payload.data ? payload.data.recommendations || [] : []);
          return;
        }
        if (payload.type === "error") {
          appendMessage("assistant", "我暫時未能識別這次回答，請直接點選下方選項再試一次。");
        }
      };
    });
  }

  async function connectNursingSocket() {
    const sessionId = await ensureSession();
    const socket = state.nursingSocket;
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      return socket;
    }
    return new Promise(function (resolve) {
      const createdSocket = new WebSocket(wsBase + "/ws/nursing/" + encodeURIComponent(sessionId));
      state.nursingSocket = createdSocket;
      createdSocket.onopen = function () {
        resolve(createdSocket);
      };
      createdSocket.onerror = function () {
        resolve(null);
      };
      createdSocket.onmessage = function (event) {
        const payload = JSON.parse(event.data);
        if (payload.type === "thinking_start") {
          showThinkingMessage();
          return;
        }
        if (payload.type === "thinking_done") {
          hideThinkingMessage();
          return;
        }
        if (payload.type === "answer_chunk") {
          appendStreamingChunk(String(payload.data.content || ""));
          return;
        }
        if (payload.type === "done") {
          finalizeStreamingMessage({
            references: payload.data && Array.isArray(payload.data.references) ? payload.data.references : [],
            safetyNotice: payload.data ? payload.data.safety_notice || "" : "",
          });
          appendMessage("assistant", "如果您還想追問其他護理問題，我可以繼續為您提供協助。");
          setStep(
            {
              kind: "nursing-ready",
              title: "護理咨詢已完成",
              hint: "您可以繼續提問，或返回服務選單。",
            },
            null,
          );
          setBusy(false);
        }
      };
    });
  }

  function presentMainMenu(skipMessage) {
    state.currentFlow = "service_menu";
    if (!skipMessage) {
      appendMessage("assistant", WELCOME_TEXT);
    }
    setStep(
      {
        kind: "menu",
        title: "請選擇您需要的服務",
        hint: "您可以選擇下方服務，或稍後使用自由輸入描述需求。",
        options: [
          { value: "nursing", title: "護理咨詢", description: "查詢日常照護方法、注意事項與護理建議。" },
          { value: "assessment", title: "輔具評估推薦", description: "逐題了解需求，精準推薦合適輔具方向。" },
          { value: "browse", title: "產品分類瀏覽", description: "按分類查看商品，了解詳情與庫存狀況。" },
          { value: "intent", title: "自由輸入需求", description: "直接描述情況，由系統識別意圖並自動分流。" },
        ],
      },
      null,
    );
  }

  function showComposer(mode) {
    if (mode === "intent") {
      setStep(
        {
          kind: "idle",
          title: "請描述您的需求",
          hint: "例如：我媽媽走路不穩，想看看有什麼輔具。",
        },
        {
          mode: "intent",
          label: "自由輸入需求",
          placeholder: "請輸入您的需求描述",
          hint: "按 Enter 送出，Shift + Enter 可換行。",
          submitText: "識別並分流",
        },
      );
      return;
    }

    if (mode === "nursing") {
      setStep(
        {
          kind: "idle",
          title: "請輸入護理問題",
          hint: "我會以對話方式回覆您，並在需要時提供參考提示。",
        },
        {
          mode: "nursing",
          label: "護理問題",
          placeholder: "例如：如何幫助老人吞嚥？",
          hint: "按 Enter 送出，Shift + Enter 可換行。",
          submitText: "送出問題",
        },
      );
      return;
    }

    if (mode === "browse_search") {
      setStep(
        {
          kind: "idle",
          title: "請輸入產品關鍵字",
          hint: "例如：輪椅、護理床、認知訓練遊戲。",
        },
        {
          mode: "browse_search",
          label: "產品搜尋",
          placeholder: "請輸入產品名稱或需求關鍵字",
          hint: "按 Enter 送出，Shift + Enter 可換行。",
          submitText: "搜尋產品",
        },
      );
      return;
    }

    if (mode === "followup_custom") {
      setStep(
        {
          kind: "idle",
          title: "請補充您的需求描述",
          hint: "可輸入重量、使用情境、空間限制或照護困難點。",
        },
        {
          mode: "followup_custom",
          label: "補充需求",
          placeholder: "例如：希望更輕便、可折疊、方便外出使用",
          hint: "按 Enter 送出，Shift + Enter 可換行。",
          submitText: "提交補充",
        },
      );
      return;
    }

    if (mode === "nested_custom") {
      setStep(
        {
          kind: "idle",
          title: "請輸入二級補充描述",
          hint: "這會用來完成更細的設備跟進判斷。",
        },
        {
          mode: "nested_custom",
          label: "二級補充",
          placeholder: "例如：主要在家中短距離移動使用",
          hint: "按 Enter 送出，Shift + Enter 可換行。",
          submitText: "提交補充",
        },
      );
    }
  }

  function translateIntent(intent) {
    if (intent === "护理咨询") {
      return "護理咨詢";
    }
    if (intent === "产品-问题解决型") {
      return "輔具評估推薦";
    }
    if (intent === "产品-浏览了解型") {
      return "產品分類瀏覽";
    }
    if (intent === "意图不清") {
      return "意圖不清";
    }
    if (intent === "拒答") {
      return "拒答";
    }
    return intent || "未知";
  }

  function normalizeFollowupOptions(rawOptions) {
    return (rawOptions || []).map(function (option, index) {
      if (typeof option === "string") {
        return { label: String(index + 1), text: option };
      }
      return {
        label: option.label || String(index + 1),
        text: option.text || option.value || option.label || "",
      };
    });
  }

  function presentAssessmentQuestion(question) {
    const normalized = {
      question: question.question || "請回答下一題。",
      options: Array.isArray(question.options) ? question.options : [],
      nodeType: question.node_type || "single_choice",
    };
    state.currentFlow = "assessment";
    appendMessage("assistant", normalized.question);
    setStep(
      {
        kind: "assessment-question",
        title: normalized.question,
        hint: normalized.nodeType === "multi_choice"
          ? "請勾選符合的選項（可多選），然後點擊確認。"
          : "請直接點選最符合的選項。",
        options: normalized.options,
        nodeType: normalized.nodeType,
      },
      null,
    );
    setBusy(false);
  }

  function presentRecommendations(items) {
    state.currentFlow = "recommendation";
    state.recommendations = items || [];
    if (items && items.length === 1 && items[0].device_tag) {
      appendMessage("assistant", "根據您的情況，我先幫您確認一下「" + items[0].content + "」的具體使用場景。");
      loadFollowupQuestion(items[0].device_tag);
      return;
    }
    appendMessage("assistant", "我已根據您的回答整理出建議方向，請選擇想繼續了解的設備類型。", {
      kind: "recommendations",
      items: state.recommendations,
    });
    setStep(
      {
        kind: "recommendations",
        title: "請選擇要繼續追問的設備方向",
        hint: "系統接著會提出該設備的後續問題，再執行庫存檢索。",
        items: state.recommendations,
      },
      null,
    );
  }

  async function startAssessmentFlow() {
    setBusy(true);
    setError(null);
    try {
      await ensureSession();
      state.currentFlow = "assessment";
      appendMessage("assistant", "好的，我會先逐步了解情況，接著再提供推薦方向。");
      const socket = await connectAssessmentSocket();
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        throw new Error("assessment_websocket_unavailable");
      }
      socket.send(JSON.stringify({ type: "start" }));
    } catch (error) {
      setError(error instanceof Error ? error.message : "無法開始評估流程");
    } finally {
      setBusy(false);
    }
  }

  async function submitAssessmentAnswer(answer, selectedOptions) {
    if (!answer && (!selectedOptions || !selectedOptions.length)) {
      return;
    }
    if (answer) {
      appendMessage("user", answer);
    }
    if (selectedOptions && selectedOptions.length) {
      appendMessage("user", selectedOptions.join("；"));
    }
    setBusy(true);
    setError(null);
    try {
      const sessionId = await ensureSession();
      const socket = await connectAssessmentSocket();
      if (socket && socket.readyState === WebSocket.OPEN) {
        if (selectedOptions && selectedOptions.length) {
          socket.send(JSON.stringify({ type: "answer", selected_options: selectedOptions }));
        } else {
          socket.send(JSON.stringify({ type: "answer", user_input: answer }));
        }
      } else {
        const body = { session_id: sessionId };
        if (selectedOptions && selectedOptions.length) {
          body.selected_options = selectedOptions;
        } else {
          body.user_input = answer;
        }
        const result = await jsonRequest("POST", "/assessment/answer", body);
        if (result.status === "question") {
          presentAssessmentQuestion(result);
        } else if (result.status === "completed" || result.status === "recommendation") {
          presentRecommendations(result.recommendations || []);
        } else {
          appendMessage("assistant", "我暫時未能識別這次回答，請直接點選下方選項再試一次。");
        }
      }
    } catch (error) {
      setError(error instanceof Error ? error.message : "提交評估答案失敗");
    } finally {
      setBusy(false);
    }
  }

  function handleMultiSelectConfirm() {
    if (!state.selectedMultiOptions.length) return;
    submitAssessmentAnswer(null, state.selectedMultiOptions);
  }

  function handleMultiSelectReset() {
    state.selectedMultiOptions = [];
    var checkboxes = document.querySelectorAll(".multi-checkbox");
    checkboxes.forEach(function (cb) { cb.checked = false; });
    var confirmBtn = document.querySelector("[data-multi-confirm]");
    if (confirmBtn) {
      confirmBtn.disabled = true;
      confirmBtn.textContent = "確認選擇";
    }
  }

  async function openBrowseCategories() {
    setBusy(true);
    setError(null);
    try {
      await ensureSession();
      if (!state.categories.length) {
        state.categories = await request("/products/categories");
      }
      state.currentFlow = "browse";
      appendMessage("assistant", "好的，請先選擇您想了解的產品分類，或改用關鍵字搜尋。");
      setStep(
        {
          kind: "browse-categories",
          title: "請選擇產品分類",
          hint: "也可以改用關鍵字搜尋，例如：輪椅、護理床。",
          categories: state.categories,
        },
        null,
      );
    } catch (error) {
      setError(error instanceof Error ? error.message : "無法載入產品分類");
    } finally {
      setBusy(false);
    }
  }

  async function loadProducts(params) {
    params = params || {};
    setBusy(true);
    setError(null);
    try {
      await ensureSession();
      const query = new URLSearchParams();
      if (params.categoryName) {
        query.set("category_name", params.categoryName);
      }
      if (params.keyword) {
        query.set("query", params.keyword);
      }
      query.set("page", String(params.page || 1));
      query.set("page_size", "6");
      const response = await request("/products?" + query.toString());
      state.currentFlow = "browse";
      state.selectedCategory = response.category ? response.category.category_name : params.categoryName || null;
      state.productView = {
        items: response.items || [],
        page: response.page || 1,
        totalPages: response.total_pages || 1,
        keyword: params.keyword || "",
        categoryName: state.selectedCategory,
      };
      appendMessage(
        "assistant",
        response.items && response.items.length
          ? "以下是目前找到的產品，您可以先查看詳情。"
          : "暫時沒有找到符合條件的產品，您可以換一個分類或關鍵字。",
      );
      setStep(
        {
          kind: "products",
          title: state.selectedCategory ? "分類：" + state.selectedCategory : "產品搜尋結果",
          hint: "您可以查看詳情、換頁、重新搜尋或重新選擇分類。",
          view: state.productView,
        },
        null,
      );
    } catch (error) {
      setError(error instanceof Error ? error.message : "載入產品列表失敗");
    } finally {
      setBusy(false);
    }
  }

  async function loadProductDetail(name) {
    setBusy(true);
    setError(null);
    try {
      const detail = await request("/products/detail?query=" + encodeURIComponent(name));
      state.productDetail = detail;
      renderDrawer();
    } catch (error) {
      setError(error instanceof Error ? error.message : "無法載入商品詳情");
    } finally {
      setBusy(false);
    }
  }

  function renderDrawer() {
    if (!state.productDetail) {
      elements.drawer.classList.add("hidden");
      return;
    }
    const detail = state.productDetail;
    elements.drawer.classList.remove("hidden");
    elements.drawerCategory.textContent = detail.category_name || "";
    elements.drawerTitle.textContent = detail.product_name || "";
    elements.drawerPrice.textContent = detail.sales_price || "-";
    elements.drawerStock.textContent = detail.stock_status || "-";
    const dimensions = detail.dimensions || {};
    elements.drawerDimensions.innerHTML = [
      "高度：" + (dimensions.height || "-"),
      "長度：" + (dimensions.length || "-"),
      "寬度：" + (dimensions.width || "-"),
    ]
      .map(function (item) {
        return "<div>" + escapeHtml(item) + "</div>";
      })
      .join("");
    elements.drawerDescription.textContent = detail.description || "暫無說明。";
  }

  function closeDrawer() {
    state.productDetail = null;
    renderDrawer();
  }

  async function loadFollowupQuestion(deviceTag) {
    setBusy(true);
    setError(null);
    try {
      const sessionId = await ensureSession();
      state.activeDeviceTag = deviceTag;
      state.activeFollowupAnswer = null;
      const result = await request(
        "/followup/question?session_id=" +
          encodeURIComponent(sessionId) +
          "&device_tag=" +
          encodeURIComponent(deviceTag),
      );
      const options = normalizeFollowupOptions(result.options);
      state.currentFlow = "followup";
      appendMessage("assistant", result.question || "請再回答一個後續問題。");
      setStep(
        {
          kind: "followup-question",
          title: result.question || "請回答後續問題",
          hint: "請點選最貼近您情況的選項；若沒有合適選項，可使用補充描述。",
          options: options,
        },
        null,
      );
    } catch (error) {
      setError(error instanceof Error ? error.message : "無法載入後續問題");
    } finally {
      setBusy(false);
    }
  }

  async function runInventorySearch(query, tag, categoryName, mode) {
    const sessionId = await ensureSession();
    const response = await jsonRequest("POST", "/inventory/search", {
      session_id: sessionId,
      query: query,
      tag: tag || null,
      category_name: categoryName || null,
      mode: mode || "semantic_rerank",
      top_k: 5,
    });
    state.inventoryResults = response.items || [];
    state.currentFlow = "inventory";
    appendMessage(
      "assistant",
      state.inventoryResults.length
        ? "以下是根據您的需求整理出的商品結果。"
        : "暫時未找到合適商品，您可以返回主選單重新嘗試。",
      {
        kind: "inventory",
        items: state.inventoryResults,
      },
    );
    setStep(
      {
        kind: "inventory",
        title: "庫存檢索結果",
        hint: "您可以回到主選單，或改為瀏覽產品分類。",
        items: state.inventoryResults,
      },
      null,
    );
  }

  async function submitFollowupAnswer(answer, nestedInput) {
    if (!state.activeDeviceTag) {
      return;
    }
    appendMessage("user", nestedInput || answer);
    setBusy(true);
    setError(null);
    try {
      const result = await jsonRequest("POST", "/followup/answer", {
        session_id: await ensureSession(),
        device_tag: state.activeDeviceTag,
        answer: answer,
        nested_input: nestedInput || null,
      });

      if (result.status === "need_nested_choice") {
        state.activeFollowupAnswer = answer;
        appendMessage("assistant", result.followup_question || "請再補充一個更細的選項。");
        setStep(
          {
            kind: "nested-followup",
            title: result.followup_question || "請選擇下一個細項",
            hint: "若仍沒有合適選項，也可以改用文字補充。",
            options: normalizeFollowupOptions(result.followup_options),
          },
          null,
        );
        return;
      }

      if (result.status === "recommendation") {
        appendMessage("assistant", "我已完成設備跟進，現在開始為您檢索合適商品。");
        await runInventorySearch(result.recommend || "", result.tag || "", result.category || "", "strict");
        return;
      }

      if (result.status === "inventory_search") {
        appendMessage("assistant", "我會根據您的補充描述進一步檢索商品。");
        await runInventorySearch(result.user_choice || nestedInput || answer, result.tag || "", result.category || "", "semantic_rerank");
        return;
      }

      if (result.status === "redirect") {
        appendMessage("assistant", "這個情況較適合轉人工或線下專業服務跟進。");
        presentMainMenu(true);
        return;
      }

      if (result.status === "no_product") {
        appendMessage("assistant", "目前這個細分類型暫時沒有可直接推薦的商品，您可以補充需求或返回主選單。");
        setStep(
          {
            kind: "idle",
            title: "暫無直接商品",
            hint: "您可以補充描述，或返回主選單重新開始。",
          },
          null,
        );
        return;
      }

      appendMessage("assistant", "我已收到您的回答，請繼續下一步。");
    } catch (error) {
      setError(error instanceof Error ? error.message : "提交設備跟進答案失敗");
    } finally {
      setBusy(false);
    }
  }

  async function openNursingFlow() {
    await ensureSession();
    state.currentFlow = "nursing";
    appendMessage("assistant", "好的，請直接告訴我您想查詢的護理問題。");
    setStep(
      {
        kind: "idle",
        title: "請輸入護理問題",
        hint: "送出後，我會以對話方式逐段回覆。",
      },
      {
        mode: "nursing",
        label: "護理問題",
        placeholder: "例如：如何幫助老人翻身？",
        hint: "按 Enter 送出，Shift + Enter 可換行。",
        submitText: "送出問題",
      },
    );
  }

  async function submitNursingQuestion(question) {
    if (!question) {
      return;
    }
    appendMessage("user", question);
    setBusy(true);
    setError(null);
    try {
      const socket = await connectNursingSocket();
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "question", question: question }));
      } else {
        const response = await jsonRequest("POST", "/nursing/ask", {
          session_id: await ensureSession(),
          question: question,
        });
        appendMessage("assistant", response.answer || "", {
          references: response.references || [],
          safetyNotice: response.safety_notice || "",
        });
        appendMessage("assistant", "如果您還想追問其他護理問題，我可以繼續為您提供協助。");
        setStep(
          {
            kind: "nursing-ready",
            title: "護理咨詢已完成",
            hint: "您可以繼續提問，或返回主選單。",
          },
          null,
        );
        setBusy(false);
      }
    } catch (error) {
      setError(error instanceof Error ? error.message : "護理咨詢失敗");
      setBusy(false);
    }
  }

  async function submitIntentInput(text) {
    if (!text) {
      return;
    }
    appendMessage("user", text);
    setBusy(true);
    setError(null);
    try {
      const result = await jsonRequest("POST", "/intent/classify", {
        session_id: await ensureSession(),
        user_input: text,
      });
      const translatedIntent = translateIntent(result.intent);

      if (result.intent === "护理咨询") {
        appendMessage("assistant", "我理解您需要「" + translatedIntent + "」，現在直接為您處理。");
        await submitNursingQuestion(text);
        return;
      }

      if (result.intent === "产品-问题解决型") {
        appendMessage("assistant", "我理解您需要「" + translatedIntent + "」，現在開始逐步問答。");
        await startAssessmentFlow();
        return;
      }

      if (result.intent === "产品-浏览了解型") {
        appendMessage("assistant", "我理解您想「" + translatedIntent + "」，先為您搜尋相關產品。");
        await loadProducts({ keyword: text, page: 1 });
        return;
      }

      if (result.intent === "拒答") {
        appendMessage("assistant", result.message || "這個問題不在我目前可協助的範圍內，請改問照護或產品相關內容。");
        presentMainMenu(true);
        return;
      }

      appendMessage("assistant", "我暫時未能準確判斷服務類型，您可以直接選擇下方服務，或再輸入一次。");
      setStep(
        {
          kind: "menu",
          title: "請重新選擇服務或再描述一次",
          hint: "若需求比較複雜，建議直接使用「自由輸入需求」。",
          options: [
            { value: "nursing", title: "護理咨詢", description: "以護理方法與照護建議為主。" },
            { value: "assessment", title: "問題解決型推薦", description: "先逐題問答，再推薦合適方向。" },
            { value: "browse", title: "瀏覽了解產品", description: "查看產品分類與商品列表。" },
            { value: "intent", title: "再描述一次", description: "重新用文字描述需求。" },
          ],
        },
        null,
      );
    } catch (error) {
      setError(error instanceof Error ? error.message : "意圖識別失敗");
    } finally {
      setBusy(false);
    }
  }

  function handleComposerSubmit(event) {
    event.preventDefault();
    const composer = state.composer;
    if (!composer) {
      return;
    }
    const value = elements.composerInput.value.trim();
    if (!value) {
      return;
    }
    elements.composerInput.value = "";

    if (composer.mode === "intent") {
      submitIntentInput(value);
      return;
    }
    if (composer.mode === "nursing") {
      submitNursingQuestion(value);
      return;
    }
    if (composer.mode === "browse_search") {
      appendMessage("user", value);
      loadProducts({ keyword: value, page: 1 });
      return;
    }
    if (composer.mode === "followup_custom") {
      submitFollowupAnswer(value);
      return;
    }
    if (composer.mode === "nested_custom") {
      submitFollowupAnswer(state.activeFollowupAnswer || "", value);
    }
  }

  function handleMainService(service) {
    if (service === "nursing") {
      appendMessage("user", "我想要護理咨詢");
      openNursingFlow();
      return;
    }
    if (service === "assessment") {
      appendMessage("user", "我想進行問題解決型推薦");
      startAssessmentFlow();
      return;
    }
    if (service === "browse") {
      appendMessage("user", "我想先瀏覽了解產品");
      openBrowseCategories();
      return;
    }
    if (service === "intent") {
      appendMessage("user", "我想自由輸入需求");
      showComposer("intent");
    }
  }

  async function resetConversation() {
    setError(null);
    setBusy(false);
    if (state.assessmentSocket && state.assessmentSocket.readyState < 2) {
      state.assessmentSocket.close();
    }
    if (state.nursingSocket && state.nursingSocket.readyState < 2) {
      state.nursingSocket.close();
    }
    state.sessionId = null;
    state.currentFlow = "idle";
    state.messages = [];
    state.step = null;
    state.composer = null;
    state.categories = [];
    state.productView = null;
    state.recommendations = [];
    state.inventoryResults = [];
    state.productDetail = null;
    state.selectedCategory = null;
    state.assessmentSocket = null;
    state.nursingSocket = null;
    state.activeDeviceTag = null;
    state.activeFollowupAnswer = null;
    stopTypingLoop();
    renderDrawer();
    renderHeader();
    await ensureSession(true);
    presentMainMenu(false);
  }

  function handleActionClick(target) {
    const mainService = target.closest("[data-main-service]");
    if (mainService) {
      handleMainService(mainService.getAttribute("data-main-service") || "");
      return;
    }
    const assessmentOption = target.closest("[data-assessment-option]");
    if (assessmentOption) {
      submitAssessmentAnswer(assessmentOption.getAttribute("data-assessment-option") || "");
      return;
    }
    const deviceTag = target.closest("[data-device-tag]");
    if (deviceTag) {
      loadFollowupQuestion(deviceTag.getAttribute("data-device-tag") || "");
      return;
    }
    const followupOption = target.closest("[data-followup-option]");
    if (followupOption) {
      const label = followupOption.getAttribute("data-followup-option") || "";
      state.activeFollowupAnswer = label;
      submitFollowupAnswer(label);
      return;
    }
    const nestedOption = target.closest("[data-nested-option]");
    if (nestedOption) {
      submitFollowupAnswer(state.activeFollowupAnswer || "", nestedOption.getAttribute("data-nested-option") || "");
      return;
    }
    const categoryNameButton = target.closest("[data-category-name]");
    if (categoryNameButton) {
      const categoryName = categoryNameButton.getAttribute("data-category-name") || "";
      appendMessage("user", "我想了解「" + categoryName + "」");
      loadProducts({ categoryName: categoryName, page: 1 });
      return;
    }
    const productNameButton = target.closest("[data-product-name]");
    if (productNameButton) {
      loadProductDetail(productNameButton.getAttribute("data-product-name") || "");
      return;
    }
    const productPager = target.closest("[data-product-page]");
    if (productPager) {
      if (!state.productView) {
        return;
      }
      const nextPage =
        productPager.getAttribute("data-product-page") === "prev"
          ? state.productView.page - 1
          : state.productView.page + 1;
      loadProducts({
        categoryName: state.productView.categoryName,
        keyword: state.productView.keyword,
        page: nextPage,
      });
      return;
    }
    const showComposerButton = target.closest("[data-show-composer]");
    if (showComposerButton) {
      showComposer(showComposerButton.getAttribute("data-show-composer") || "");
      return;
    }
    if (target.closest("[data-browse-categories]")) {
      openBrowseCategories();
      return;
    }
    if (target.closest("[data-return-menu]")) {
      presentMainMenu(false);
    }
  }

  document.addEventListener("click", function (event) {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    if (target.id === "drawerClose" || target.closest("[data-close-drawer='true']")) {
      closeDrawer();
      return;
    }
    const multiConfirm = target.closest("[data-multi-confirm]");
    if (multiConfirm) {
      handleMultiSelectConfirm();
      return;
    }
    const multiReset = target.closest("[data-multi-reset]");
    if (multiReset) {
      handleMultiSelectReset();
      return;
    }
    handleActionClick(target);
  });

  document.addEventListener("change", function (event) {
    const checkbox = event.target;
    if (!(checkbox instanceof HTMLInputElement)) return;
    if (!checkbox.classList.contains("multi-checkbox")) return;
    const checked = checkbox.checked;
    const value = checkbox.value;
    if (checked) {
      if (state.selectedMultiOptions.indexOf(value) === -1) {
        state.selectedMultiOptions.push(value);
      }
    } else {
      const idx = state.selectedMultiOptions.indexOf(value);
      if (idx !== -1) state.selectedMultiOptions.splice(idx, 1);
    }
    const confirmBtn = document.querySelector("[data-multi-confirm]");
    if (confirmBtn) {
      confirmBtn.disabled = state.selectedMultiOptions.length === 0;
      confirmBtn.textContent = state.selectedMultiOptions.length > 0
        ? "確認選擇（" + state.selectedMultiOptions.length + "）"
        : "確認選擇";
    }
  });

  elements.restartButton.addEventListener("click", function () {
    resetConversation().catch(function (error) {
      setError(error instanceof Error ? error.message : "重新開始失敗");
    });
  });

  elements.composerForm.addEventListener("submit", handleComposerSubmit);

  elements.composerInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      elements.composerForm.requestSubmit();
    }
  });

  Promise.resolve()
    .then(function () {
      return ensureSession();
    })
    .then(function () {
      presentMainMenu(false);
    })
    .catch(function (error) {
      setError(error instanceof Error ? error.message : "初始化失敗");
    });
})();
