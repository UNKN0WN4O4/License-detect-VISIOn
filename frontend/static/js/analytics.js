/**
 * Urban Traffic Analytics & Chart.js Visualizations
 * BEL / City Traffic Operations Command Center
 */

class TrafficAnalytics {
  constructor() {
    this.charts = {};
  }

  init() {
    this.initHourlyVolumeChart();
    this.initVehicleDistributionChart();
    this.initCongestedNodesChart();
    this.initViolationsTrendChart();
    this.startLiveKPIUpdates();
  }

  // Chart 1: Hourly Traffic Volume (Peak vs Normal)
  initHourlyVolumeChart() {
    const ctx = document.getElementById('chart-hourly-volume');
    if (!ctx) return;

    const hours = ['00:00', '02:00', '04:00', '06:00', '08:00', '10:00', '12:00', '14:00', '16:00', '18:00', '20:00', '22:00'];
    const currentVolume = [1200, 650, 420, 1850, 6890, 8420, 5600, 6100, 7950, 9120, 6400, 3100];
    const historicalAvg = [1100, 600, 400, 1600, 6200, 7800, 5200, 5800, 7400, 8600, 5900, 2800];

    this.charts.hourlyVolume = new Chart(ctx, {
      type: 'line',
      data: {
        labels: hours,
        datasets: [
          {
            label: 'Today (Live Volume)',
            data: currentVolume,
            borderColor: '#00f2fe',
            backgroundColor: 'rgba(0, 242, 254, 0.15)',
            fill: true,
            tension: 0.4,
            borderWidth: 2,
            pointBackgroundColor: '#00f2fe',
            pointRadius: 4,
            pointHoverRadius: 6
          },
          {
            label: 'Historical Baseline (30-Day Avg)',
            data: historicalAvg,
            borderColor: '#64748b',
            borderDash: [5, 5],
            backgroundColor: 'transparent',
            tension: 0.4,
            borderWidth: 2,
            pointRadius: 0
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            labels: { color: '#94a3b8', font: { family: 'Outfit', size: 12 } }
          },
          tooltip: {
            backgroundColor: 'rgba(13, 22, 41, 0.95)',
            titleColor: '#00f2fe',
            bodyColor: '#ffffff',
            borderColor: 'rgba(0, 242, 254, 0.3)',
            borderWidth: 1
          }
        },
        scales: {
          x: {
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: { color: '#64748b', font: { family: 'Share Tech Mono' } }
          },
          y: {
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: { color: '#64748b', font: { family: 'Share Tech Mono' } }
          }
        }
      }
    });
  }

  // Chart 2: Vehicle Distribution (Donut Chart)
  initVehicleDistributionChart() {
    const ctx = document.getElementById('chart-vehicle-dist');
    if (!ctx) return;

    this.charts.vehicleDist = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: ['Sedan', 'SUV / 4x4', 'Two-Wheeler', 'Commercial / Truck', 'EV Cab / Auto', 'Bus'],
        datasets: [{
          data: [38, 24, 18, 11, 6, 3],
          backgroundColor: [
            '#00f2fe',
            '#38bdf8',
            '#6366f1',
            '#f59e0b',
            '#10b981',
            '#ef4444'
          ],
          borderColor: '#0d1322',
          borderWidth: 3,
          hoverOffset: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'right',
            labels: { color: '#94a3b8', font: { family: 'Outfit', size: 11 }, padding: 12 }
          },
          tooltip: {
            backgroundColor: 'rgba(13, 22, 41, 0.95)',
            callbacks: {
              label: (context) => ` ${context.label}: ${context.raw}%`
            }
          }
        },
        cutout: '68%'
      }
    });
  }

  // Chart 3: Top Congested Nodes (Horizontal Bar Chart)
  initCongestedNodesChart() {
    const ctx = document.getElementById('chart-congested-nodes');
    if (!ctx) return;

    const nodes = ['IFFCO Chowk Flyover', 'Kherki Daula Toll', 'AIIMS South Extn', 'MG Road Metro Jct', 'Shankar Chowk Cloverleaf'];
    const delayScores = [84, 78, 72, 58, 52]; // Congestion Index 0 - 100

    this.charts.congestedNodes = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: nodes,
        datasets: [{
          label: 'Congestion & Delay Index (%)',
          data: delayScores,
          backgroundColor: (ctx) => {
            const v = ctx.raw;
            if (v >= 75) return '#ef4444';
            if (v >= 60) return '#f59e0b';
            return '#10b981';
          },
          borderRadius: 6,
          borderSkipped: false
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: 'rgba(13, 22, 41, 0.95)',
            callbacks: {
              label: (context) => ` Delay Index: ${context.raw}% (Est. Wait +14 mins)`
            }
          }
        },
        scales: {
          x: {
            max: 100,
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: { color: '#64748b', font: { family: 'Share Tech Mono' } }
          },
          y: {
            grid: { display: false },
            ticks: { color: '#cbd5e1', font: { family: 'Outfit', size: 11 } }
          }
        }
      }
    });
  }

  // Chart 4: Speed Violations & Watchlist Hits Trend
  initViolationsTrendChart() {
    const ctx = document.getElementById('chart-violations-trend');
    if (!ctx) return;

    const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const speeding = [142, 168, 155, 189, 230, 310, 275];
    const watchlistMatches = [12, 15, 9, 21, 18, 28, 24];

    this.charts.violationsTrend = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: days,
        datasets: [
          {
            label: 'Over-speeding Violations',
            data: speeding,
            backgroundColor: 'rgba(245, 158, 11, 0.75)',
            borderRadius: 4
          },
          {
            label: 'Watchlist / Hotlist Hits',
            data: watchlistMatches,
            backgroundColor: '#ef4444',
            borderRadius: 4
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            labels: { color: '#94a3b8', font: { family: 'Outfit', size: 11 } }
          },
          tooltip: {
            backgroundColor: 'rgba(13, 22, 41, 0.95)'
          }
        },
        scales: {
          x: {
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: { color: '#64748b', font: { family: 'Share Tech Mono' } }
          },
          y: {
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: { color: '#64748b', font: { family: 'Share Tech Mono' } }
          }
        }
      }
    });
  }

  startLiveKPIUpdates() {
    // Dynamic micro-increments to simulate live command center operations
    setInterval(() => {
      const liveDpm = document.getElementById('kpi-dpm');
      if (liveDpm) {
        const base = 438;
        const jitter = Math.floor(Math.random() * 24) - 12;
        liveDpm.textContent = base + jitter;
      }

      const totalDetections = document.getElementById('kpi-total-plates');
      if (totalDetections) {
        let current = parseInt(totalDetections.textContent.replace(/,/g, ''), 10) || 128450;
        current += Math.floor(1 + Math.random() * 3);
        totalDetections.textContent = current.toLocaleString();
      }

      const avgSpeed = document.getElementById('kpi-avg-speed');
      if (avgSpeed) {
        const spd = 48.5 + (Math.random() * 1.4 - 0.7);
        avgSpeed.textContent = `${spd.toFixed(1)} km/h`;
      }
    }, 3000);
  }
}

window.TrafficAnalytics = TrafficAnalytics;
