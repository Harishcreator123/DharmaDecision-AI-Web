
document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("form");
  const input =
    document.getElementById("dilemma") ||
    document.querySelector("textarea");

  const analyzeButton =
    document.getElementById("analyzeButton") ||
    document.querySelector(
      'button[type="submit"], button'
    );

  let results =
    document.getElementById("results");

  if (!results) {
    results = document.createElement("section");
    results.id = "results";
    results.style.cssText =
      "max-width:900px;margin:30px auto;padding:24px;" +
      "background:#fff;border:1px solid #ddd;" +
      "border-radius:14px;display:none;";

    const main =
      document.querySelector("main") ||
      document.body;

    const questionBox =
      input?.closest("form") ||
      input?.parentElement;

    if (questionBox) {
      questionBox.insertAdjacentElement(
        "afterend",
        results
      );
    } else {
      main.appendChild(results);
    }
  }

  function escapeHTML(value) {
    return String(value ?? "").replace(
      /[&<>"']/g,
      char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      })[char]
    );
  }

  function showError(message) {
    results.style.display = "block";
    results.innerHTML =
      `<h2>Analysis could not be completed</h2>` +
      `<p>${escapeHTML(message)}</p>`;
    results.scrollIntoView({
      behavior: "smooth",
      block: "start"
    });
  }

  async function analyze() {
    const dilemma = input?.value?.trim();

    if (!dilemma) {
      showError("Please enter an ethical dilemma first.");
      return;
    }

    analyzeButton.disabled = true;
    results.style.display = "block";
    results.innerHTML = "<p>Analyzing your dilemma…</p>";

    try {
      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ dilemma })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.error || `Server returned ${response.status}`
        );
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
      showError(error.message || "Unknown error.");
    } finally {
      analyzeButton.disabled = false;
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
