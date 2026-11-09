/**
 * Rehab Voice 2025 - Main JavaScript
 * Utilidades y funciones compartidas
 */

// ==================== CONFIGURACIÓN ====================
const CONFIG = {
    API_BASE: '',
    PATIENT_ID: 'default',
    LANGUAGE: 'es',
    VOICE: 'es-ES-AlvaroNeural'
};

// ==================== ESTADO GLOBAL ====================
const AppState = {
    isRecording: false,
    mediaRecorder: null,
    audioChunks: [],
    currentWord: null,
    sessionStats: {
        attempts: 0,
        correct: 0,
        totalScore: 0
    }
};

// ==================== UTILIDADES DE AUDIO ====================
class AudioRecorder {
    constructor() {
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.stream = null;
    }

    async start() {
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    sampleRate: 16000
                }
            });

            this.mediaRecorder = new MediaRecorder(this.stream, {
                mimeType: 'audio/webm;codecs=opus'
            });

            this.audioChunks = [];

            this.mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) {
                    this.audioChunks.push(e.data);
                }
            };

            this.mediaRecorder.start(100); // Collect data every 100ms
            return true;
        } catch (error) {
            console.error('Error al acceder al micrófono:', error);
            throw error;
        }
    }

    stop() {
        return new Promise((resolve) => {
            if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
                this.mediaRecorder.onstop = () => {
                    const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
                    this.cleanup();
                    resolve(audioBlob);
                };
                this.mediaRecorder.stop();
            } else {
                resolve(null);
            }
        });
    }

    cleanup() {
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }
        this.mediaRecorder = null;
        this.audioChunks = [];
    }
}

// ==================== API CLIENT ====================
class APIClient {
    static async get(endpoint) {
        const response = await fetch(`${CONFIG.API_BASE}${endpoint}`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        return response.json();
    }

    static async post(endpoint, data) {
        const response = await fetch(`${CONFIG.API_BASE}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        return response.json();
    }

    static async postFormData(endpoint, formData) {
        const response = await fetch(`${CONFIG.API_BASE}${endpoint}`, {
            method: 'POST',
            body: formData
        });
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        return response.json();
    }

    // Métodos específicos
    static async getCategories() {
        return this.get('/api/categories');
    }

    static async getWords(category, level = 1) {
        return this.get(`/api/words/${category}?level=${level}`);
    }

    static async analyzeVoice(audioBlob, targetWord) {
        const formData = new FormData();
        formData.append('audio_file', audioBlob, 'recording.webm');
        formData.append('target_word', targetWord);
        return this.postFormData('/api/analyze-voice', formData);
    }

    static async getProgress(patientId = CONFIG.PATIENT_ID) {
        return this.get(`/api/progress/${patientId}`);
    }

    static async saveProgress(data) {
        return this.post('/api/progress', data);
    }

    static async getDailyChallenge() {
        return this.get('/api/games/daily-challenge');
    }

    static async getAchievements(patientId = CONFIG.PATIENT_ID) {
        return this.get(`/api/games/achievements/${patientId}`);
    }
}

// ==================== UTILIDADES DE UI ====================
const UI = {
    // Mobile Menu Toggle
    toggleMobileMenu() {
        const menu = document.getElementById('mobile-menu');
        const icon = document.getElementById('menu-icon');

        if (menu) {
            menu.classList.toggle('active');
            // Toggle accessible state
            const isExpanded = menu.classList.contains('active');
            document.getElementById('mobile-menu-btn')?.setAttribute('aria-expanded', isExpanded);

            // Toggle Icon
            if (icon) {
                if (isExpanded) {
                    icon.classList.remove('fa-bars');
                    icon.classList.add('fa-times');
                } else {
                    icon.classList.remove('fa-times');
                    icon.classList.add('fa-bars');
                }
            }
        }
    },

    // Toggle Settings
    toggleSettings() {
        alert("Configuración próximamente...");
    },

    // Mostrar notificación
    notify(message, type = 'info') {
        const colors = {
            success: 'bg-green-500',
            error: 'bg-red-500',
            warning: 'bg-yellow-500',
            info: 'bg-blue-500'
        };

        const notification = document.createElement('div');
        notification.className = `fixed top-4 right-4 ${colors[type]} text-white px-6 py-3 rounded-xl shadow-lg z-50 animate-fadeIn`;
        notification.textContent = message;
        document.body.appendChild(notification);

        setTimeout(() => {
            notification.classList.add('opacity-0', 'transition-opacity');
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    },

    // Mostrar loading
    showLoading(container) {
        const loader = document.createElement('div');
        loader.id = 'loading-overlay';
        loader.className = 'absolute inset-0 bg-white/80 flex items-center justify-center z-10';
        loader.innerHTML = '<div class="spinner"></div>';
        container.style.position = 'relative';
        container.appendChild(loader);
    },

    hideLoading(container) {
        const loader = container.querySelector('#loading-overlay');
        if (loader) loader.remove();
    },

    // Actualizar puntos en header
    updatePoints(points) {
        const pointsEl = document.getElementById('total-points') ||
            document.getElementById('session-points');
        if (pointsEl) {
            pointsEl.textContent = points;
            pointsEl.classList.add('animate-bounce');
            setTimeout(() => pointsEl.classList.remove('animate-bounce'), 500);
        }
        localStorage.setItem('total_points', points);
    },

    // Formatear fecha
    formatDate(dateString) {
        const date = new Date(dateString);
        return date.toLocaleDateString('es', {
            day: 'numeric',
            month: 'short',
            hour: '2-digit',
            minute: '2-digit'
        });
    },

    // Crear elemento de puntuación circular
    createScoreCircle(score, size = 100) {
        const circumference = 2 * Math.PI * 45;
        const offset = circumference - (score / 100) * circumference;
        const color = score >= 70 ? '#10b981' : score >= 50 ? '#f59e0b' : '#ef4444';

        return `
            <svg width="${size}" height="${size}" viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="45" fill="none" stroke="#e5e7eb" stroke-width="8"/>
                <circle cx="50" cy="50" r="45" fill="none" stroke="${color}" stroke-width="8"
                        stroke-dasharray="${circumference}" stroke-dashoffset="${offset}"
                        stroke-linecap="round" transform="rotate(-90 50 50)"
                        class="score-circle"/>
                <text x="50" y="55" text-anchor="middle" class="text-2xl font-bold" fill="#1f2937">
                    ${Math.round(score)}%
                </text>
            </svg>
        `;
    }
};

// ==================== ALMACENAMIENTO LOCAL ====================
const Storage = {
    get(key, defaultValue = null) {
        const value = localStorage.getItem(key);
        if (value === null) return defaultValue;
        try {
            return JSON.parse(value);
        } catch {
            return value;
        }
    },

    set(key, value) {
        localStorage.setItem(key, JSON.stringify(value));
    },

    remove(key) {
        localStorage.removeItem(key);
    },

    // Helpers específicos
    getPatientId() {
        return this.get('patient_id', 'default');
    },

    getTotalPoints() {
        return this.get('total_points', 0);
    },

    addPoints(points) {
        const total = this.getTotalPoints() + points;
        this.set('total_points', total);
        return total;
    }
};

// ==================== REPRODUCTOR DE AUDIO ====================
class AudioPlayer {
    constructor() {
        this.audio = new Audio();
    }

    async playWord(word, voice = CONFIG.VOICE) {
        try {
            this.audio.src = `/api/speak/${encodeURIComponent(word)}?voice=${voice}`;
            await this.audio.play();
        } catch (error) {
            console.error('Error reproduciendo audio:', error);
            UI.notify('Error al reproducir audio', 'error');
        }
    }

    stop() {
        this.audio.pause();
        this.audio.currentTime = 0;
    }
}

// ==================== VISUALIZADOR DE AUDIO ====================
class AudioVisualizer {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) return;

        this.ctx = this.canvas.getContext('2d');
        this.analyser = null;
        this.dataArray = null;
        this.animationId = null;
    }

    start(stream) {
        if (!this.canvas) return;

        const audioContext = new AudioContext();
        const source = audioContext.createMediaStreamSource(stream);
        this.analyser = audioContext.createAnalyser();
        this.analyser.fftSize = 256;
        source.connect(this.analyser);

        const bufferLength = this.analyser.frequencyBinCount;
        this.dataArray = new Uint8Array(bufferLength);

        this.draw();
    }

    draw() {
        if (!this.analyser) return;

        this.animationId = requestAnimationFrame(() => this.draw());

        this.analyser.getByteFrequencyData(this.dataArray);

        const width = this.canvas.width;
        const height = this.canvas.height;
        const barWidth = (width / this.dataArray.length) * 2.5;

        this.ctx.fillStyle = '#f3f4f6';
        this.ctx.fillRect(0, 0, width, height);

        let x = 0;
        for (let i = 0; i < this.dataArray.length; i++) {
            const barHeight = (this.dataArray[i] / 255) * height;

            const gradient = this.ctx.createLinearGradient(0, height, 0, height - barHeight);
            gradient.addColorStop(0, '#6366f1');
            gradient.addColorStop(1, '#8b5cf6');

            this.ctx.fillStyle = gradient;
            this.ctx.fillRect(x, height - barHeight, barWidth, barHeight);

            x += barWidth + 1;
        }
    }

    stop() {
        if (this.animationId) {
            cancelAnimationFrame(this.animationId);
            this.animationId = null;
        }
        if (this.canvas) {
            this.ctx.fillStyle = '#f3f4f6';
            this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
        }
    }
}

// ==================== INICIALIZACIÓN ====================
document.addEventListener('DOMContentLoaded', () => {
    // Cargar puntos guardados
    const savedPoints = Storage.getTotalPoints();
    const pointsEl = document.getElementById('total-points');
    if (pointsEl) {
        pointsEl.textContent = savedPoints;
    }

    // Verificar soporte de audio
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        UI.notify('Tu navegador no soporta grabación de audio', 'warning');
    }
});

// Exportar para uso global
window.AudioRecorder = AudioRecorder;
window.APIClient = APIClient;
window.UI = UI;
window.Storage = Storage;
window.AudioPlayer = AudioPlayer;
window.AudioVisualizer = AudioVisualizer;
window.CONFIG = CONFIG;
