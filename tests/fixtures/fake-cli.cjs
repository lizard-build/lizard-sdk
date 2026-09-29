#!/usr/bin/env node
// Local fixture: no network, filesystem writes or payment signing.
let input = ''
process.stdin.setEncoding('utf8')
process.stdin.on('data', chunk => { input += chunk })
process.stdin.on('end', () => {
  if (process.argv.includes('fail')) {
    process.stdout.write(JSON.stringify({ error: 'expected failure' }))
    process.exitCode = 3
    return
  }
  process.stdout.write(JSON.stringify({ args: process.argv.slice(2), input }) + '\n')
})
