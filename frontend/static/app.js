
document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("form");
  const input =
    document.getElementById("dilemma") ||
    document.querySelector("textarea");

  const analyzeButton =
    document.getElementById("analyzeButton") ||
    document.querySelector('button[type="submit"], button');

  let results = document.getElementById("results");

  if (!results) {
    results = document.createElement("section");
    results.id = "results";
    results.style.cssText =
      "max-width:900px;margin:30px auto;padding:24px;" +
      "background:#fff;border:1px solid #ddd;" +
      "border-radius:14px;display:none;";

    const questionBox =
      input?.closest("form") || input?.parentElement;

    if (questionBox) {
      questionBox.insertAdjacentElement("afterend", results);
    } else {
      (document.querySelector("main") || document.body)
        .appendChild(results);
    }
  }

  function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    })[char]);
  }

  function showError(title, message) {
    results.style.display = "block";
    results.innerHTML =
      `<h2>${escapeHTML(title)}</h2>` +
      `<p>${escapeHTML(message)}</p>`;

    results.scrollIntoView({
      behavior: "smooth",
      block: "start"
    });
  }

  function getHttpError(response, data) {
    switch (response.status) {
      case 400:
        return {
          title: "Invalid Request",
          message: data.error ||
            "Your request could not be processed. Please check your dilemma and try again."
        };

      case 404:
        return {
          title: "Analysis Service Not Found",
          message:
            "The analysis endpoint could not be found. Please contact the administrator."
        };

      case 408:
        return {
          title: "Request Timed Out",
          message:
            "The server took too long to process your request. Please try again."
        };

      case 429:
        return {
          title: "Too Many Requests",
          message:
            "Too many analysis requests were sent in a short time. Please wait a moment and try again."
        };

      case 500:
        return {
          title: "Internal Server Error",
          message:
            "The analysis server encountered an internal error while processing your dilemma. Please try again later."
        };

      case 502:
        return {
          title: "Analysis Service Temporarily Unavailable",
          message:
            "The server gateway could not obtain a valid response from the analysis service. Please try again shortly."
        };

      case 503:
        return {
          title: "Analysis Service Unavailable",
          message:
            "The analysis service is temporarily unavailable. Please try again later."
        };

      case 504:
        return {
          title: "Server Timeout",
          message:
            "The server gateway waited too long for the analysis service. Please try again."
        };

      default:
        return {
          title: "Analysis Request Failed",
          message:
            `The server returned HTTP ${response.status}. Please try again later.`
        };
    }
  }

  async function analyze() {
    const dilemma = input?.value?.trim() || "";

    if (!dilemma) {
      showError(
        "Dilemma Required",
        "Please enter an ethical dilemma before clicking Analyze Decision."
      );
      input?.focus();
      return;
    }

    if (dilemma.length < 10) {
      showError(
        "More Details Needed",
        "Please describe your ethical dilemma in at least 10 characters so the system has enough information to analyze it."
      );
      input?.focus();
      return;
    }

    if (analyzeButton) {
      analyzeButton.disabled = true;
    }

    results.style.display = "block";
    results.innerHTML = "<p>Analyzing your dilemma…</p>";

    let timeoutId;

    try {
      const controller = new AbortController();

      timeoutId = setTimeout(() => controller.abort(), 30000);

      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ dilemma }),
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      const contentType = response.headers.get("content-type") || "";
      let data = {};

      if (contentType.includes("application/json")) {
        try {
          data = await response.json();
        } catch {
          showError(
            "Invalid Server Response",
            "The server returned unreadable JSON. Please try again later."
          );
          return;
        }
      } else if (!response.ok) {
        const errorInfo = getHttpError(response, {});
        showError(errorInfo.title, errorInfo.message);
        return;
      } else {
        showError(
          "Unexpected Server Response",
          "The server did not return the expected analysis data. Please try again later."
        );
        return;
      }

      if (!response.ok) {
        const errorInfo = getHttpError(response, data);
        showError(errorInfo.title, errorInfo.message);
        return;
      }

      const evidence = Array.isArray(data.evidence)
        ? data.evidence
        : [];

      const evidenceHTML = evidence.length
        ? evidence.map(item => `
            <article style="
              border:1px solid #ddd;
              border-radius:10px;
              padding:16px;
              margin:12px 0;
            ">
              <h3>${escapeHTML(item.principle)}</h3>
              <p>${escapeHTML(item.text)}</p>
              <p><small>
                ${escapeHTML(item.source)}
                ${item.evidence_type
                  ? " · " + escapeHTML(item.evidence_type)
                  : ""}
              </small></p>
            </article>
          `).join("")
        : "<p>No sufficiently relevant supporting passages were found in the current knowledge base.</p>";

      results.innerHTML = `
        <h2>Decision Analysis</h2>

        <p><strong>Your dilemma:</strong>
          ${escapeHTML(data.dilemma || dilemma)}
        </p>

        <h3>Recommendation</h3>
        <p>${escapeHTML(
          data.recommendation ||
          data.message ||
          "No recommendation was returned."
        )}</p>

        <p><strong>Evidence relevance:</strong>
          ${escapeHTML(data.relevance_status || "Not assessed")}
        </p>

        <p><strong>Confidence:</strong>
          ${escapeHTML(
            data.confidence_label ||
            "Not statistically validated"
          )}
        </p>

        ${data.message
          ? `<p>${escapeHTML(data.message)}</p>`
          : ""}

        <h3>Retrieved Evidence</h3>
        ${evidenceHTML}

        <p style="font-size:12px;color:#666;">
          This is decision support, not a definitive moral
          judgment. Retrieved paraphrases should be checked
          against a reliable source before academic citation.
        </p>
      `;

      results.style.display = "block";
      results.scrollIntoView({
        behavior: "smooth",
        block: "start"
      });

    } catch (error) {
      if (timeoutId) clearTimeout(timeoutId);

      if (error.name === "AbortError") {
        showError(
          "Analysis Timed Out",
          "The analysis did not respond within 30 seconds. The server may be starting up or taking too long. Please try again."
        );
      } else if (error instanceof TypeError) {
        showError(
          "Connection Failed",
          "Unable to connect to the analysis server. Please check your internet connection or try again when the server is available."
        );
      } else {
        showError(
          "Unexpected Error",
          "An unexpected problem occurred while analyzing your dilemma. Please try again."
        );
      }
    } finally {
      if (analyzeButton) {
        analyzeButton.disabled = false;
      }
    }
  }

  if (form) {
    form.addEventListener("submit", event => {
      event.preventDefault();
      analyze();
    });
  }

  if (analyzeButton && !form) {
    analyzeButton.addEventListener("click", event => {
      event.preventDefault();
      analyze();
    });
  }
});
