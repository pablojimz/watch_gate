const cors = require('cors');

// ruleid: express-cors-wildcard-credentials
app.use(cors({ origin: true, credentials: true }));

// ruleid: express-cors-wildcard-credentials
app.use(cors({ credentials: true, origin: true }));

// ok: express-cors-wildcard-credentials
app.use(cors({ origin: ['https://app.example.com'], credentials: true }));

// ok: express-cors-wildcard-credentials
app.use(cors({ origin: true }));
