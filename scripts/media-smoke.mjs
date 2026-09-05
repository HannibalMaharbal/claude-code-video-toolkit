import { spawn } from 'node:child_process'
import { mkdir } from 'node:fs/promises'

const output = 'output/ci-smoke.webm'
const command = process.platform === 'win32' ? 'npm.cmd' : 'npm'
const args = [
  'exec', '--', 'remotion', 'render', 'templates/product-demo/src/index.ts', 'TransitionGallery', output,
  '--frames=0-2', '--scale=0.1', '--codec=vp8', '--concurrency=1', '--log=verbose',
]

await mkdir('output', { recursive: true })

const child = spawn(command, args, { stdio: 'inherit', env: process.env })
const timeout = setTimeout(() => {
  child.kill('SIGTERM')
  setTimeout(() => child.kill('SIGKILL'), 5_000).unref()
}, 120_000)

const exitCode = await new Promise((resolve, reject) => {
  child.once('error', reject)
  child.once('exit', (code, signal) => resolve(code ?? (signal ? 1 : 0)))
})
clearTimeout(timeout)
if (exitCode !== 0) process.exit(exitCode)

const validator = spawn('uv', ['run', 'python', 'tools/media_validation.py', 'video', output], { stdio: 'inherit' })
const validationCode = await new Promise((resolve, reject) => {
  validator.once('error', reject)
  validator.once('exit', (code, signal) => resolve(code ?? (signal ? 1 : 0)))
})
process.exit(validationCode)
