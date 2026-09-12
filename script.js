let samples = [];
let recording = false;
let startTime = 0;

// Update this with your teammate's ngrok URL when they send it!
const BACKEND_URL = "https://[THE-NGROK-URL]/api/tremor"; 

document.getElementById('startBtn').addEventListener('click', async () => {
    
    // Request sensor permissions (Required for some browsers)
    if (typeof DeviceMotionEvent !== 'undefined' && typeof DeviceMotionEvent.requestPermission === 'function') {
        try {
            const perm = await DeviceMotionEvent.requestPermission();
            if (perm !== 'granted') {
                alert("Sensor permission denied."); 
                return;
            }
        } catch (e) {
            alert("Error requesting sensors.");
            return;
        }
    }

    // Update UI
    document.getElementById('startBtn').classList.add('hidden');
    document.getElementById('statusText').classList.remove('hidden');
    document.getElementById('resultsUI').classList.add('hidden');

    samples = [];
    recording = true;
    startTime = performance.now(); // Mark the exact start time

    // Capture and convert rotation data
    const listener = (event) => {
        if (!recording) return;
        const rot = event.rotationRate || {};
        
        // Convert milliseconds to seconds from the start of the test
        const timeInSeconds = (performance.now() - startTime) / 1000.0;
        const degToRad = Math.PI / 180.0;

        samples.push({
            time: timeInSeconds,
            gyro_x: (rot.beta || 0) * degToRad,
            gyro_y: (rot.gamma || 0) * degToRad,
            gyro_z: (rot.alpha || 0) * degToRad
        });
    };

    window.addEventListener('devicemotion', listener);

    // Record for exactly 10 seconds (as requested by the README)
    await new Promise(r => setTimeout(r, 10000));
    
    recording = false;
    window.removeEventListener('devicemotion', listener);
    document.getElementById('statusText').innerText = "Sending data to backend...";

    // Send data to the Flask API
    try {
        const response = await fetch(BACKEND_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ samples: samples })
        });
        
        const data = await response.json();
        
        // Map the backend's specific JSON response to your HTML elements
        document.getElementById('statusText').classList.add('hidden');
        document.getElementById('resultsUI').classList.remove('hidden');
        
        // Display the plain-language reasons provided by the backend
        document.getElementById('resVerdict').innerText = data.flag_doctor ? "Consultation Recommended" : "Normal Baseline";
        document.getElementById('resFreq').innerText = data.reasons[0] || "Analysis Complete";
        
    } catch (err) {
        alert("Failed to connect. Is the backend running and CORS enabled?");
        console.error(err);
    }
    
    // Reset UI
    document.getElementById('startBtn').classList.remove('hidden');
    document.getElementById('startBtn').innerText = "Test Again";
});