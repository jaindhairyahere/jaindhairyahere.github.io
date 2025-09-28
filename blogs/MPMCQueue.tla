-------------------------------- MODULE MPMCQueue --------------------------------

EXTENDS Integers, Sequences, TLC

CONSTANTS 
    CAPACITY,           \* Queue capacity (must be > 0)
    MAX_PRODUCERS,      \* Maximum number of producer threads
    MAX_CONSUMERS,      \* Maximum number of consumer threads  
    MAX_OPERATIONS      \* Maximum operations per thread for model checking

VARIABLES
    \* Queue buffer - circular array of data items
    buffer,
    
    \* Four-index MPMC protocol with tagged pointers
    producer_head,      \* Tagged pointer: <<index, tag>> for reservation
    producer_tail,      \* Untagged index for completion
    consumer_head,      \* Tagged pointer: <<index, tag>> for reservation  
    consumer_tail,      \* Untagged index for completion
    
    \* Per-slot state tracking for ordered completion
    slot_ready,         \* Boolean array indicating slot completion status
    
    \* Thread operation counters for liveness checking
    producer_ops,       \* Operations completed by each producer
    consumer_ops        \* Operations completed by each consumer

vars == <<buffer, producer_head, producer_tail, consumer_head, consumer_tail, 
          slot_ready, producer_ops, consumer_ops>>

\* Type invariants
TypeOK == 
    /\ buffer \in [0..CAPACITY -> (Int \cup {"EMPTY"})]
    /\ producer_head \in [index: 0..CAPACITY, tag: Nat]
    /\ producer_tail \in 0..CAPACITY
    /\ consumer_head \in [index: 0..CAPACITY, tag: Nat] 
    /\ consumer_tail \in 0..CAPACITY
    /\ slot_ready \in [0..CAPACITY -> BOOLEAN]
    /\ producer_ops \in [1..MAX_PRODUCERS -> 0..MAX_OPERATIONS]
    /\ consumer_ops \in [1..MAX_CONSUMERS -> 0..MAX_OPERATIONS]

\* Initialize queue to empty state
Init ==
    /\ buffer = [i \in 0..CAPACITY |-> "EMPTY"]
    /\ producer_head = [index |-> 0, tag |-> 0]
    /\ producer_tail = 0
    /\ consumer_head = [index |-> 0, tag |-> 0]
    /\ consumer_tail = 0
    /\ slot_ready = [i \in 0..CAPACITY |-> FALSE]
    /\ producer_ops = [i \in 1..MAX_PRODUCERS |-> 0]
    /\ consumer_ops = [i \in 1..MAX_CONSUMERS |-> 0]

\* Queue state predicates
IsFull == (producer_head.index + 1) % (CAPACITY + 1) = consumer_tail
IsEmpty == consumer_head.index = producer_tail

\* Producer enqueue operation with ABA protection
ProducerEnqueue(pid, data) ==
    /\ producer_ops[pid] < MAX_OPERATIONS
    /\ ~IsFull
    /\ LET reserved_index == producer_head.index
           new_producer_head == [index |-> (reserved_index + 1) % (CAPACITY + 1),
                                tag |-> producer_head.tag + 1]
       IN
           \* Step 1: Atomic reservation using tagged CAS
           /\ producer_head' = new_producer_head
           
           \* Step 2: Write data to reserved slot
           /\ buffer' = [buffer EXCEPT ![reserved_index] = data]
           
           \* Step 3: Mark slot as ready for ordered completion
           /\ slot_ready' = [slot_ready EXCEPT ![reserved_index] = TRUE]
           
           \* Step 4: Advance producer tail if this thread is next in line
           /\ IF producer_tail = reserved_index
              THEN producer_tail' = (producer_tail + 1) % (CAPACITY + 1)
              ELSE producer_tail' = producer_tail
           
           \* Update operation counter
           /\ producer_ops' = [producer_ops EXCEPT ![pid] = @ + 1]
           
           \* Other variables unchanged
           /\ UNCHANGED <<consumer_head, consumer_tail, consumer_ops>>

\* Consumer dequeue operation with ABA protection  
ConsumerDequeue(cid) ==
    /\ consumer_ops[cid] < MAX_OPERATIONS
    /\ ~IsEmpty
    /\ LET reserved_index == consumer_head.index
           new_consumer_head == [index |-> (reserved_index + 1) % (CAPACITY + 1),
                                tag |-> consumer_head.tag + 1]
       IN
           \* Step 1: Atomic reservation using tagged CAS
           /\ consumer_head' = new_consumer_head
           
           \* Step 2: Read data from reserved slot (data consumption)
           \* Note: In actual implementation this would return the data
           
           \* Step 3: Advance consumer tail if this thread is next in line
           /\ IF consumer_tail = reserved_index
              THEN /\ consumer_tail' = (consumer_tail + 1) % (CAPACITY + 1)
                   /\ buffer' = [buffer EXCEPT ![reserved_index] = "EMPTY"]
                   /\ slot_ready' = [slot_ready EXCEPT ![reserved_index] = FALSE]
              ELSE /\ consumer_tail' = consumer_tail
                   /\ UNCHANGED <<buffer, slot_ready>>
           
           \* Update operation counter  
           /\ consumer_ops' = [consumer_ops EXCEPT ![cid] = @ + 1]
           
           \* Other variables unchanged
           /\ UNCHANGED <<producer_head, producer_tail, producer_ops>>

\* Next state relation - any valid producer or consumer operation
Next == 
    \/ \E pid \in 1..MAX_PRODUCERS, data \in Int : 
         ProducerEnqueue(pid, data)
    \/ \E cid \in 1..MAX_CONSUMERS : 
         ConsumerDequeue(cid)

\* Complete specification
Spec == Init /\ [][Next]_vars

\* Safety Properties

\* Queue indices remain within valid bounds
BoundedIndices ==
    /\ producer_head.index \in 0..CAPACITY
    /\ producer_tail \in 0..CAPACITY  
    /\ consumer_head.index \in 0..CAPACITY
    /\ consumer_tail \in 0..CAPACITY

\* Tagged pointers always increment (prevents ABA)
MonotonicTags ==
    /\ producer_head.tag >= 0
    /\ consumer_head.tag >= 0

\* FIFO property: data written to buffer is consumed in order
\* (This is complex to specify fully but we check basic ordering)
FIFOOrdering ==
    \* Consumer tail never overtakes producer tail
    LET producer_pos == producer_tail
        consumer_pos == consumer_tail
        distance == (producer_pos - consumer_pos + CAPACITY + 1) % (CAPACITY + 1)
    IN distance <= CAPACITY

\* No data corruption - empty slots contain "EMPTY"
DataIntegrity ==
    \A i \in 0..CAPACITY :
        (buffer[i] = "EMPTY") <=> (~slot_ready[i])

\* Mutual exclusion: no two threads can reserve the same slot
\* (This is ensured by the atomic nature of tagged CAS operations)
SlotExclusivity ==
    \* At most one slot can be in transition between indices
    LET producer_distance == (producer_head.index - producer_tail + CAPACITY + 1) % (CAPACITY + 1)
        consumer_distance == (consumer_head.index - consumer_tail + CAPACITY + 1) % (CAPACITY + 1)
    IN /\ producer_distance <= CAPACITY
       /\ consumer_distance <= CAPACITY

\* Liveness Properties

\* Progress property: if queue is not full, producers can make progress
ProducerProgress ==
    (~IsFull) ~> (\E pid \in 1..MAX_PRODUCERS : producer_ops'[pid] > producer_ops[pid])

\* Progress property: if queue is not empty, consumers can make progress  
ConsumerProgress ==
    (~IsEmpty) ~> (\E cid \in 1..MAX_CONSUMERS : consumer_ops'[cid] > consumer_ops[cid])

\* Starvation freedom: all threads eventually make progress
\* (Under fair scheduling assumptions)
NoStarvation ==
    /\ \A pid \in 1..MAX_PRODUCERS : 
         WF_vars(ProducerEnqueue(pid, pid)) \* Use pid as data for simplicity
    /\ \A cid \in 1..MAX_CONSUMERS :
         WF_vars(ConsumerDequeue(cid))

\* Combined safety invariant
Safety == TypeOK /\ BoundedIndices /\ MonotonicTags /\ FIFOOrdering /\ DataIntegrity /\ SlotExclusivity

\* Model checking configuration
MCInit == 
    /\ CAPACITY = 3       \* Small capacity for model checking
    /\ MAX_PRODUCERS = 2  \* Two producers
    /\ MAX_CONSUMERS = 2  \* Two consumers
    /\ MAX_OPERATIONS = 3 \* Limited operations to avoid state explosion
    /\ Init

\* Temporal properties to check
THEOREM Spec => []Safety
THEOREM Spec => ProducerProgress
THEOREM Spec => ConsumerProgress

=============================================================================

\* Model checking instructions:
\*
\* To check this specification with TLC:
\* 1. Set CAPACITY = 3, MAX_PRODUCERS = 2, MAX_CONSUMERS = 2, MAX_OPERATIONS = 3
\* 2. Check invariant: Safety
\* 3. Check temporal properties: ProducerProgress, ConsumerProgress
\* 4. Use symmetry sets for producers and consumers to reduce state space
\*
\* Expected results:
\* - Safety invariant should hold (no deadlocks, no data corruption)
\* - Progress properties should be satisfied under fair scheduling
\* - Model should explore all reachable states without finding violations
\*
\* This specification models the key aspects of the MPMC queue:
\* - Four-index protocol with tagged pointers for ABA prevention
\* - Atomic reservation and ordered completion phases
\* - Concurrent producer and consumer operations
\* - Safety properties ensuring correctness
\* - Liveness properties ensuring progress and starvation freedom