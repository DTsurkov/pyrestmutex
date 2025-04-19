let maxTtl = 30; // used for scaling progress bar (can adjust per row later)

async function fetchLocks() {
    const res = await fetch('/locks');
    const locks = await res.json();
    const tbody = document.querySelector('#locks tbody');
    tbody.innerHTML = '';
    locks.forEach(lock => {
        const row = document.createElement('tr');

        // Row color
        let rowClass = "";
        if (lock.ttl_left <= 3) rowClass = "row-red";
        else if (lock.ttl_left <= 10) rowClass = "row-yellow";
        else rowClass = "row-green";

        row.className = rowClass;

        const progress = Math.min(lock.ttl_left / maxTtl, 1.0) * 100;
        const unlockBtn = (lock.owner === document.getElementById("owner").value.trim())
            ? `<button onclick="unlock('${lock.name}')">Unlock</button>`
            : '';

        row.innerHTML = `
                    <td>${lock.name}</td>
                    <td>${lock.owner}</td>
                    <td>${new Date(lock.expires_at * 1000).toLocaleString()}</td>
                    <td>${lock.ttl_left}s</td>
                    <td><div class="ttl-bar" style="width: ${progress}%; background-color: ${progressColor(progress)};"></div></td>
                    <td>${unlockBtn}</td>
                `;
        tbody.appendChild(row);
    });
}

function progressColor(pct) {
    if (pct > 33) return '#4CAF50'; // green
    if (pct > 10) return '#FFEB3B'; // yellow
    return '#f44336'; // red
}

async function lock() {
    const name = document.getElementById("lockName").value.trim();
    const owner = document.getElementById("owner").value.trim();
    const ttl = parseInt(document.getElementById("ttl").value);
    if (!name || !owner || !ttl) return alert("Fill in all fields.");
    maxTtl = ttl;
    const res = await fetch(`/lock/${name}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ owner, ttl })
    });
    const data = await res.json();
    alert(data.status === "locked" ? "Lock acquired." : `Already locked by ${data.owner}`);
    await fetchLocks();
}

async function renew() {
    const name = document.getElementById("lockName").value.trim();
    const owner = document.getElementById("owner").value.trim();
    const ttl = parseInt(document.getElementById("ttl").value);
    if (!name || !owner || !ttl) return alert("Fill in all fields.");
    maxTtl = ttl;
    const res = await fetch(`/renew/${name}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ owner, ttl })
    });
    if (res.ok) {
        alert("Lock renewed.");
    } else {
        const msg = await res.text();
        alert("Failed to renew: " + msg);
    }
    await fetchLocks();
}

async function unlock(name) {
    const owner = document.getElementById("owner").value.trim();
    if (!owner) {
        alert("Please enter your name before unlocking.");
        return;
    }
    const res = await fetch(`/unlock/${name}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ owner })
    });
    if (res.ok) {
        alert(`Lock '${name}' released.`);
    } else {
        const msg = await res.text();
        alert(`Error releasing lock: ${msg}`);
    }
    await fetchLocks();
}

async function fetchLog() {
    const res = await fetch('/log');
    const log = await res.json();
    const tbody = document.querySelector('#log tbody');
    tbody.innerHTML = '';
    log.forEach(entry => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${new Date(entry.timestamp * 1000).toLocaleString()}</td>
            <td>${entry.name}</td>
            <td>${entry.owner}</td>
            <td>${entry.action}</td>
        `;
        tbody.appendChild(row);
    });
}

document.getElementById("owner").addEventListener("input", fetchLocks);
fetchLocks();

setInterval(() => {
    fetchLocks();
    fetchLog();
}, 500);