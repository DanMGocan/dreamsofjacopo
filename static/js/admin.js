// Track active requests
let activeStatusUpdates = {};
let activeSystemActions = {
    killLibreOffice: null,
    restartApp: null
};
let activeFetches = {
    stats: null,
    bugReports: null
};

// Global function to update bug report status
function updateBugStatus(reportId, newStatus) {
    if (confirm(`Are you sure you want to update the status of bug report #${reportId}?`)) {
        // Abort previous request for this report if it exists
        if (activeStatusUpdates[reportId] instanceof AbortController) {
            activeStatusUpdates[reportId].abort();
        }
        
        // Create new abort controller
        activeStatusUpdates[reportId] = new AbortController();
        const signal = activeStatusUpdates[reportId].signal;
        
        fetch(`/api/system/bug_reports/${reportId}/status`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ status: newStatus }),
            signal: signal
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            alert(data.message);
            // Refresh the bug reports table
            document.getElementById('refreshBugReports').click();
        })
        .catch(error => {
            if (error.name !== 'AbortError') {
                console.error('Error updating bug status:', error);
                alert('Failed to update bug status');
            }
        });
    }
}

// Global function to show full bug description in a modal
function showFullDescription(description) {
    // Create modal elements
    const modalBackdrop = document.createElement('div');
    modalBackdrop.className = 'modal-backdrop fade show';
    document.body.appendChild(modalBackdrop);
    
    const modalHtml = `
        <div class="modal fade show" style="display: block;" tabindex="-1">
            <div class="modal-dialog modal-dialog-centered modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Bug Description</h5>
                        <button type="button" class="btn-close" onclick="closeModal()"></button>
                    </div>
                    <div class="modal-body">
                        <p style="white-space: pre-wrap;">${description}</p>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" onclick="closeModal()">Close</button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    const modalContainer = document.createElement('div');
    modalContainer.id = 'descriptionModal';
    modalContainer.innerHTML = modalHtml;
    document.body.appendChild(modalContainer);
    
    // Prevent scrolling of the background
    document.body.style.overflow = 'hidden';
}

// Global function to close the modal
function closeModal() {
    // Remove modal elements
    const modal = document.getElementById('descriptionModal');
    if (modal) {
        modal.remove();
    }
    
    const backdrop = document.querySelector('.modal-backdrop');
    if (backdrop) {
        backdrop.remove();
    }
    
    // Re-enable scrolling
    document.body.style.overflow = '';
}

document.addEventListener('DOMContentLoaded', function() {
    // Initialize gauges
    const cpuGauge = createGauge('cpuGauge', 'CPU Usage');
    const memoryGauge = createGauge('memoryGauge', 'Memory Usage');
    const diskGauge = createGauge('diskGauge', 'Disk Usage');
    
    
    // Fetch system stats initially
    fetchSystemStats();
    
    // Fetch bug reports initially
    fetchBugReports();
    
    // Set up auto-refresh every 15 seconds
    const refreshInterval = setInterval(fetchSystemStats, 15000);
    
    // Clean up on page unload
    window.addEventListener('beforeunload', function() {
        // Clear interval
        clearInterval(refreshInterval);
        
        // Abort any active fetches
        for (const key in activeFetches) {
            if (activeFetches[key] instanceof AbortController) {
                activeFetches[key].abort();
            }
        }
        
        // Abort any active system action requests
        for (const key in activeSystemActions) {
            if (activeSystemActions[key] instanceof AbortController) {
                activeSystemActions[key].abort();
            }
        }
        
        // Abort any active status update requests
        for (const key in activeStatusUpdates) {
            if (activeStatusUpdates[key] instanceof AbortController) {
                activeStatusUpdates[key].abort();
            }
        }
    });
    
    // Manual refresh buttons
    document.getElementById('refreshSystemStats').addEventListener('click', fetchSystemStats);
    document.getElementById('refreshBugReports').addEventListener('click', fetchBugReports);
    
    
    // System action buttons
    document.getElementById('killLibreOfficeBtn').addEventListener('click', function() {
        if (confirm('Are you sure you want to kill all LibreOffice processes?')) {
            // Abort previous request if it exists
            if (activeSystemActions.killLibreOffice instanceof AbortController) {
                activeSystemActions.killLibreOffice.abort();
            }
            
            // Create new abort controller
            activeSystemActions.killLibreOffice = new AbortController();
            const signal = activeSystemActions.killLibreOffice.signal;
            
            fetch('/api/system/kill-libreoffice', { 
                method: 'POST',
                signal: signal
            })
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                    fetchSystemStats(); // Refresh stats after action
                })
                .catch(error => {
                    if (error.name !== 'AbortError') {
                        console.error('Error:', error);
                        alert('Failed to kill LibreOffice processes');
                    }
                });
        }
    });
    
    document.getElementById('restartAppBtn').addEventListener('click', function() {
        if (confirm('Are you sure you want to restart the application? This will disconnect all users.')) {
            // Abort previous request if it exists
            if (activeSystemActions.restartApp instanceof AbortController) {
                activeSystemActions.restartApp.abort();
            }
            
            // Create new abort controller
            activeSystemActions.restartApp = new AbortController();
            const signal = activeSystemActions.restartApp.signal;
            
            fetch('/api/system/restart-app', { 
                method: 'POST',
                signal: signal
            })
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                })
                .catch(error => {
                    if (error.name !== 'AbortError') {
                        console.error('Error:', error);
                        alert('Failed to restart application');
                    }
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
    
    // Status labels and colors for bug reports
    const statusLabels = {
        0: { text: 'Pending', class: 'bg-secondary' },
        1: { text: 'Investigating', class: 'bg-warning' },
        2: { text: 'Resolved', class: 'bg-success' },
        3: { text: 'Not a Bug', class: 'bg-info' }
    };
    
    // Fetch bug reports from API
    function fetchBugReports() {
        // Abort previous fetch if it exists
        if (activeFetches.bugReports instanceof AbortController) {
            activeFetches.bugReports.abort();
        }
        
        // Create new abort controller
        activeFetches.bugReports = new AbortController();
        const signal = activeFetches.bugReports.signal;
        
        fetch('/api/system/bug_reports', { signal })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                const bugReportsTable = document.getElementById('bugReportsTable');
                bugReportsTable.innerHTML = '';
                
                if (data.bug_reports && data.bug_reports.length > 0) {
                    data.bug_reports.forEach(report => {
                        const row = document.createElement('tr');
                        
                        // Format the created date
                        const createdDate = new Date(report.created_at);
                        const formattedDate = createdDate.toLocaleDateString() + ' ' + createdDate.toLocaleTimeString();
                        
                        // Create status badge
                        const statusInfo = statusLabels[report.status] || { text: 'Unknown', class: 'bg-secondary' };
                        const statusBadge = `<span class="badge ${statusInfo.class}">${statusInfo.text}</span>`;
                        
                        // Create action buttons for status changes
                        let actionButtons = '';
                        Object.entries(statusLabels).forEach(([statusValue, statusInfo]) => {
                            if (parseInt(statusValue) !== report.status) {
                                actionButtons += `
                                    <button class="btn btn-sm btn-outline-primary mb-1 me-1" 
                                            onclick="updateBugStatus(${report.report_id}, ${statusValue})">
                                        Mark as ${statusInfo.text}
                                    </button>
                                `;
                            }
                        });
                        
                        // Truncate long descriptions for display
                        let displayDescription = report.bug_description;
                        if (displayDescription.length > 100) {
                            displayDescription = displayDescription.substring(0, 100) + '...';
                        }
                        
                        // Create the row HTML
                        row.innerHTML = `
                            <td>${report.report_id}</td>
                            <td>
                                <div>${displayDescription}</div>
                                <button class="btn btn-sm btn-link p-0" 
                                        onclick="showFullDescription('${report.bug_description.replace(/'/g, "\\'")}')">
                                    View Full
                                </button>
                            </td>
                            <td>${report.email}</td>
                            <td>${formattedDate}</td>
                            <td>${statusBadge}</td>
                            <td>
                                <div class="d-flex flex-wrap">
                                    ${actionButtons}
                                </div>
                            </td>
                        `;
                        
                        bugReportsTable.appendChild(row);
                    });
                } else {
                    bugReportsTable.innerHTML = '<tr><td colspan="6" class="text-center">No bug reports found</td></tr>';
                }
            })
            .catch(error => {
                if (error.name !== 'AbortError') {
                    console.error('Error fetching bug reports:', error);
                    document.getElementById('bugReportsTable').innerHTML = 
                        '<tr><td colspan="6" class="text-center text-danger">Error fetching bug reports</td></tr>';
                }
            });
    }
    
    // Fetch system stats from API
    function fetchSystemStats() {
        // Abort previous fetch if it exists
        if (activeFetches.stats instanceof AbortController) {
            activeFetches.stats.abort();
        }
        
        // Create new abort controller
        activeFetches.stats = new AbortController();
        const signal = activeFetches.stats.signal;
        
        fetch('/api/system/stats', { signal })
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
                if (error.name !== 'AbortError') {
                    console.error('Error fetching system stats:', error);
                    document.getElementById('cpuInfo').textContent = 'Error fetching data';
                    document.getElementById('memoryInfo').textContent = 'Error fetching data';
                    document.getElementById('diskInfo').textContent = 'Error fetching data';
                    document.getElementById('topProcessesTable').innerHTML = '<tr><td colspan="4" class="text-center text-danger">Error fetching process data</td></tr>';
                    document.getElementById('libreofficeProcesses').innerHTML = '<div class="alert alert-danger">Error fetching process data</div>';
                }
            });
    }
});
