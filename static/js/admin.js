document.addEventListener('DOMContentLoaded', function() {
    // Initialize gauges
    const cpuGauge = createGauge('cpuGauge', 'CPU Usage');
    const memoryGauge = createGauge('memoryGauge', 'Memory Usage');
    const diskGauge = createGauge('diskGauge', 'Disk Usage');
    
    // Fetch system stats initially
    fetchSystemStats();
    
    // Set up auto-refresh every 15 seconds
    const refreshInterval = setInterval(fetchSystemStats, 15000);
    
    // Manual refresh button
    document.getElementById('refreshSystemStats').addEventListener('click', fetchSystemStats);
    
    // System action buttons
    document.getElementById('killLibreOfficeBtn').addEventListener('click', function() {
        if (confirm('Are you sure you want to kill all LibreOffice processes?')) {
            fetch('/api/system/kill-libreoffice', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                    fetchSystemStats(); // Refresh stats after action
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('Failed to kill LibreOffice processes');
                });
        }
    });
    
    document.getElementById('restartAppBtn').addEventListener('click', function() {
        if (confirm('Are you sure you want to restart the application? This will disconnect all users.')) {
            fetch('/api/system/restart-app', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('Failed to restart application');
                });
        }
    });
    
    // Create gauge chart
    function createGauge(canvasId, label) {
        const ctx = document.getElementById(canvasId).getContext('2d');
        return new Chart(ctx, {
            type: 'doughnut',
            data: {
                datasets: [{
                    data: [0, 100],
                    backgroundColor: ['#00308F', '#f1f1f1'],
                    borderWidth: 0
                }]
            },
            options: {
                cutout: '75%',
                responsive: true,
                maintainAspectRatio: false,
                circumference: 180,
                rotation: -90,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        enabled: false
                    }
                }
            }
        });
    }
    
    // Update gauge with new value
    function updateGauge(gauge, value) {
        gauge.data.datasets[0].data = [value, 100 - value];
        gauge.update();
    }
    
    // Format uptime
    function formatUptime(days, hours, minutes) {
        return `${days}d ${hours}h ${minutes}m`;
    }
    
    // Fetch system stats from API
    function fetchSystemStats() {
        fetch('/api/system/stats')
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                // Update CPU gauge
                const cpuPercent = data.cpu.percent;
                updateGauge(cpuGauge, cpuPercent);
                document.getElementById('cpuValue').textContent = `${cpuPercent}%`;
                document.getElementById('cpuInfo').textContent = `Current CPU usage`;
                
                // Update Memory gauge
                const memoryPercent = data.memory.percent;
                const memoryUsedMB = data.memory.used_mb;
                const memoryTotalMB = data.memory.total_mb;
                updateGauge(memoryGauge, memoryPercent);
                document.getElementById('memoryValue').textContent = `${memoryPercent}%`;
                document.getElementById('memoryInfo').textContent = `${memoryUsedMB.toFixed(0)} MB / ${memoryTotalMB.toFixed(0)} MB`;
                
                // Update Disk gauge
                const diskPercent = data.disk.percent;
                const diskUsedGB = data.disk.used_gb;
                const diskTotalGB = data.disk.total_gb;
                updateGauge(diskGauge, diskPercent);
                document.getElementById('diskValue').textContent = `${diskPercent}%`;
                document.getElementById('diskInfo').textContent = `${diskUsedGB.toFixed(1)} GB / ${diskTotalGB.toFixed(1)} GB`;
                
                // Update uptime
                const days = data.uptime.days;
                const hours = data.uptime.hours;
                const minutes = data.uptime.minutes;
                document.getElementById('uptimeDisplay').textContent = formatUptime(days, hours, minutes);
                document.getElementById('uptimeInfo').textContent = `System has been running since ${new Date(Date.now() - data.uptime.total_seconds * 1000).toLocaleString()}`;
                
                // Update top processes table
                const topProcessesTable = document.getElementById('topProcessesTable');
                topProcessesTable.innerHTML = '';
                
                if (data.top_processes && data.top_processes.length > 0) {
                    data.top_processes.forEach(process => {
                        const row = document.createElement('tr');
                        row.innerHTML = `
                            <td>${process.name}</td>
                            <td>${process.pid}</td>
                            <td>${process.cpu_percent.toFixed(1)}%</td>
                            <td>${process.memory_percent.toFixed(1)}%</td>
                        `;
                        topProcessesTable.appendChild(row);
                    });
                } else {
                    topProcessesTable.innerHTML = '<tr><td colspan="4" class="text-center">No significant processes found</td></tr>';
                }
                
                // Update LibreOffice processes
                const libreofficeProcessesDiv = document.getElementById('libreofficeProcesses');
                if (data.libreoffice_processes && data.libreoffice_processes.length > 0) {
                    let html = '<div class="table-responsive"><table class="table table-sm table-hover">';
                    html += '<thead><tr><th>Process</th><th>PID</th><th>CPU %</th><th>Memory %</th></tr></thead><tbody>';
                    
                    data.libreoffice_processes.forEach(process => {
                        html += `<tr>
                            <td>${process.name}</td>
                            <td>${process.pid}</td>
                            <td>${process.cpu_percent.toFixed(1)}%</td>
                            <td>${process.memory_percent.toFixed(1)}%</td>
                        </tr>`;
                    });
                    
                    html += '</tbody></table></div>';
                    libreofficeProcessesDiv.innerHTML = html;
                } else {
                    libreofficeProcessesDiv.innerHTML = '<div class="alert alert-info">No LibreOffice processes currently running</div>';
                }
                
                // Update last updated time
                const now = new Date();
                document.getElementById('lastUpdated').textContent = `Last updated: ${now.toLocaleTimeString()}`;
            })
            .catch(error => {
                console.error('Error fetching system stats:', error);
                document.getElementById('cpuInfo').textContent = 'Error fetching data';
                document.getElementById('memoryInfo').textContent = 'Error fetching data';
                document.getElementById('diskInfo').textContent = 'Error fetching data';
                document.getElementById('topProcessesTable').innerHTML = '<tr><td colspan="4" class="text-center text-danger">Error fetching process data</td></tr>';
                document.getElementById('libreofficeProcesses').innerHTML = '<div class="alert alert-danger">Error fetching process data</div>';
            });
    }
});
