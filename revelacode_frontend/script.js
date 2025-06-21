
document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("decode-form");
    const input = document.getElementById("verse-input");
    const resultText = document.getElementById("result");

    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        const verse = input.value.trim();
        if (!verse) {
            resultText.textContent = "Please enter a verse.";
            return;
        }

        resultText.textContent = "Decoding...";

        try {
            const response = await fetch("https://revelacode-backend.onrender.com/decode", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ verse })
            });

            const data = await response.json();
            console.log("Backend response:", data);

            if (data.status === "success") {
                resultText.textContent = data.decoded;
            } else {
                resultText.textContent = data.message || "Something went wrong.";
            }

        } catch (error) {
            console.error("Fetch error:", error);
            resultText.textContent = "Error reaching backend.";
        }
    });
});
