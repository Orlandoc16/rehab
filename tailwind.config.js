/** @type {import('tailwindcss').Config} */
// Configuración única de Tailwind para todas las páginas (antes estaba duplicada en cada plantilla).
// Generar el CSS:  npm run build:css   (o  npm run watch:css  mientras desarrollas)
module.exports = {
  content: ['./templates/**/*.html', './static/js/**/*.js'],
  theme: {
    extend: {
      fontFamily: {
        poppins: ['Poppins', 'sans-serif'],
      },
      colors: {
        primary: '#4f46e5', // indigo-600: contraste 6,3:1 con texto blanco
        secondary: '#8b5cf6',
        accent: '#f43f5e',
        success: '#10b981',
        warning: '#f59e0b',
      },
      boxShadow: {
        soft: '0 4px 20px -2px rgba(0, 0, 0, 0.1)',
        'inner-strong': 'inset 0 2px 4px 0 rgba(0, 0, 0, 0.06)',
      },
    },
  },
  plugins: [],
};
