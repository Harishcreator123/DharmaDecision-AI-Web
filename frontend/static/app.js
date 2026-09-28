const analyzeButton = document.getElementById("analyzeButton");
const dilemmaInput = document.getElementById("dilemma");

analyzeButton.addEventListener("click", async () => {

    const dilemma = dilemmaInput.value.trim();

    if (!dilemma) {
        alert("Please enter a dilemma.");
        return;
    }

    // Show that a new analysis is happening
    analyzeButton.disabled = true;
    analyzeButton.textContent = "Analyzing...";

    const recommendationBox = document.getElementById("recommendation");
    const confidenceBox = document.getElementById("confidence");
    const evidenceContainer = document.getElementById("evidenceContainer");

    recommendationBox.textContent = "Analyzing your dilemma...";
    confidenceBox.textContent = "--%";
    evidenceContainer.innerHTML = "";

    try {

        const response = await fetch("/api/analyze", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                dilemma: dilemma
            })
        });

        const data = await response.json();

        console.log("API RESPONSE:", data);

        if (!response.ok) {
            throw new Error(data.error || "Analysis failed");
        }

        // REAL recommendation from Flask
        recommendationBox.textContent = data.recommendation;

        // REAL confidence from Flask
        confidenceBox.textContent = data.confidence + "%";

        // REAL evidence from Flask
        data.evidence.forEach((item) => {

            const card = document.createElement("div");

            card.className = "evidence-card";

            card.innerHTML = `
    <h3>${item.principle || item.title || item.name || "Vidura Niti Principle"}</h3>

    <span class="source-type">
        ${item.source_type || "Paraphrase"}
    </span>

    <p>${item.text}</p>

    <small>${item.source}</small>
`;

            evidenceContainer.appendChild(card);
        });

        // Show results
        document.getElementById("results").style.display = "block";
        document.getElementById("results").classList.remove("hidden");

        document.getElementById("results").scrollIntoView({
            behavior: "smooth"
        });

    } catch (error) {

        console.error("ERROR:", error);

        recommendationBox.textContent =
            "Unable to analyze the dilemma.";

        confidenceBox.textContent = "--%";

        alert("Error connecting to the decision engine.");

    } finally {

        analyzeButton.disabled = false;
        analyzeButton.textContent = "Analyze Decision";
    }
});