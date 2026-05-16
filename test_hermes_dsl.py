import asyncio
from sovereign_swarm.protocols.hermes_v2 import HermesV2
from sovereign_swarm.protocols.hermes_wiring import HermesWiring
from sovereign_swarm.dsl import DeterministicSovereignLoop

async def test():
    bus = HermesV2()
    wiring = HermesWiring(bus)
    loop = DeterministicSovereignLoop()
    wiring.register_dsl_loop(loop)
    wiring.wire_all()
    await bus.start()
    
    result = await bus.send('dsl', {'action': 'run', 'goal': 'test hermes integration', 'requester_id': 'hermes_test'})
    print('Hermes DSL result:', result)
    
    status = await bus.send('dsl', {'action': 'status'})
    print('DSL status:', status)
    
    print('All channels:', bus.status()['handlers_registered'])
    
    await bus.stop()

asyncio.run(test())
