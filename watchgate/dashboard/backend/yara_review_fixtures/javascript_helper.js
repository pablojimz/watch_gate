// Fragmento benigno de ejemplo: un helper JS normal.

function formatCurrency(amount, currency = "EUR") {
  return new Intl.NumberFormat("es-ES", { style: "currency", currency }).format(amount);
}

async function fetchUserProfile(userId) {
  const response = await fetch(`/api/users/${userId}`);
  if (!response.ok) {
    throw new Error(`No se pudo cargar el perfil de ${userId}`);
  }
  return response.json();
}

module.exports = { formatCurrency, fetchUserProfile };
