from .config import *
from .repl import SwarmREPL
from .tests import TestRunner


async def main():
    parser = argparse.ArgumentParser(description="Sovereign Swarm v2.0 — Modular Multi-Agent OS")
    parser.add_argument("--seed", action="store_true", help="Bootstrap database")
    parser.add_argument("--repl", action="store_true", help="Start REPL")
    parser.add_argument("--test", choices=["unit", "stress", "fuzz", "safety", "integration", "adversarial", "dsl", "all"], help="Run test suite")
    parser.add_argument("--dsl", action="store_true", help="Run DeterministicSovereignLoop")
    parser.add_argument("--run-mission", type=str, default=None, help="Pass a mission goal to the DSL")
    parser.add_argument("--daemon", action="store_true", help="Start DSL daemon with Hermes bus")
    parser.add_argument("--mobile-bridge", action="store_true", help="Start mobile REST API bridge")
    args = parser.parse_args()

    if args.daemon:
        from .dsl.daemon import DSLDaemon
        daemon = DSLDaemon()
        def handle_sig(signum, frame):
            asyncio.create_task(daemon.stop())
        signal.signal(signal.SIGINT, handle_sig)
        signal.signal(signal.SIGTERM, handle_sig)
        await daemon.start()
        sys.exit(0)

    if args.mobile_bridge:
        from api.mobile_bridge import main as mobile_main
        mobile_main()
        sys.exit(0)

    if args.dsl or args.run_mission:
        from .dsl import DeterministicSovereignLoop
        loop = DeterministicSovereignLoop()
        goal = args.run_mission or input("Mission goal: ")
        result = await loop.run(goal, requester_id="cli")
        print(json.dumps(result.to_dict(), indent=2, default=str))
        sys.exit(0 if result.ok else 1)

    if args.test:
        runner = TestRunner()
        if args.test == "unit": await runner.run_unit()
        elif args.test == "stress": await runner.run_stress()
        elif args.test == "fuzz": await runner.run_fuzz()
        elif args.test == "safety": await runner.run_safety()
        elif args.test == "integration": await runner.run_integration()
        elif args.test == "adversarial": await runner.run_adversarial()
        elif args.test == "dsl": await runner.run_dsl()
        elif args.test == "all": ok = await runner.run_all(); sys.exit(0 if ok else 1)
        print(f"\nResults: {runner.passed} passed, {runner.failed} failed")
        sys.exit(0 if runner.failed == 0 else 1)

    swarm = SwarmREPL()
    def handle_sig(sig, frame):
        print("\n[signal] Shutdown requested")
        asyncio.get_event_loop().call_soon(asyncio.create_task, swarm.shutdown())
    signal.signal(signal.SIGINT, handle_sig)

    if args.seed: await swarm.seed()
    if args.repl: await swarm.repl_loop()
    elif not args.seed: parser.print_help()
    await swarm.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
