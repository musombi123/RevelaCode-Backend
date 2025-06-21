document.getElementById("decodeForm").addEventListener("submit", async function (e) {
    e.preventDefault();
    const verse = document.getElementById("verseInput").value;
  
    try {
      const response = await fetch("https://revelacode-backend.onrender.com/decode", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ verse: verse }),
      });
  
      const data = await response.json();
  
      if (data.status === "success") {
        document.getElementById("result").innerText = data.decoded;
      } else {
        document.getElementById("result").innerText = `Error: ${data.message}`;
      }
  
    } catch (error) {
      document.getElementById("result
  
});
