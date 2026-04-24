from .config import *
from .repl import SwarmREPL
from .tests import TestRunner


async def main():
    parser = argparse.ArgumentParser(description="Sovereign Swarm v1.4 — Monolithic Edition")
    parser.add_argument("--seed", action="store_true", help="Bootstrap database")
    parser.add_argument("--repl", action="store_true", help="Start REPL")
    parser.add_argument("--test", choices=["unit", "stress", "fuzz", "safety", "integration", "adversarial", "all"], help="Run test suite")
    args = parser.parse_args()

    if args.test:
        runner = TestRunner()
        if args.test == "unit": await runner.run_unit()
        elif args.test == "stress": await runner.run_stress()
        elif args.test == "fuzz": await runner.run_fuzz()
        elif args.test == "safety": await runner.run_safety()
        elif args.test == "integration": await runner.run_integration()
        elif args.test == "adversarial": await runner.run_adversarial()
        elif args.test == "all": ok = await runner.run_all(); sys.exit(0 if ok else 1)
        print(f"\nResults: {runner.passed} passed, {runner.failed} failed")
        sys.exit(0 if runner.failed == 0 else 1)

    swarm = SwarmREPL()
    def handle_sig(sig, frame):
        print("\n[signal] Shutdown requested."); asyncio.create_task(swarm.shutdown()); sys.exit(0)
    signal.signal(signal.SIGINT, handle_sig)

    if args.seed: await swarm.seed()
    if args.repl: await swarm.repl_loop()
    elif not args.seed: parser.print_help()
    await swarm.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
