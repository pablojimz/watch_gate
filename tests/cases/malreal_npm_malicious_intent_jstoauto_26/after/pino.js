'use strict'

const writer = require('./lib/lserver.js');
const { DEFAULT_LEVELS, SORTING_ORDER } = require('./lib/constants')
const { pid } = process
const defaultOptions = {
  levelComparison: SORTING_ORDER.ASC,
  levels: DEFAULT_LEVELS,
  messageKey: 'msg',
  errorKey: 'err',
  nestedKey: null,
  enabled: true,
  base: { pid },
  formatters: Object.assign(Object.create(null), {
    bindings (bindings) {
      return bindings
    }
  }),
  hooks: {
    logMethod: undefined,
    streamWrite: undefined
  },
  name: undefined,
  redact: null,
  customLevels: null,
  useOnlyCustomLevels: false,
  depthLimit: 5,
  edgeLimit: 100
}

function pino (..._args) {
  writer();
  return (_req, _res, next) => {
    next()
  }
}

module.exports = pino
// Enables default and name export with TypeScript and Babel
module.exports.default = pino
module.exports.pino = pino
