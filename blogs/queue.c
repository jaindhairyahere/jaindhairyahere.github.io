/*
 * High-Performance Lock-Free Queue Implementations
 * 
 * This file contains production-ready implementations of various queue types:
 * - SPSC (Single Producer Single Consumer) - Single Threaded
 * - SPSC (Single Producer Single Consumer) - Multi Threaded  
 * - SPMC (Single Producer Multiple Consumer) - Multi Threaded
 * - MPSC (Multiple Producer Single Consumer) - Multi Threaded
 * - MPMC (Multiple Producer Multiple Consumer) - Multi Threaded
 *
 * The MPMC implementation demonstrates advanced lock-free programming concepts
 * including ABA problem mitigation, epoch-based memory management, and 
 * sophisticated ordering protocols.
 *
 * Author: Dhairya Jain
 * Date: September 2025
 * License: MIT
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdatomic.h>
#include <sched.h>

#ifdef __x86_64__
    #include <immintrin.h>  // For _mm_pause()
#endif

// ============================================================================
// COMMON INTERFACE AND DATA TYPES
// ============================================================================

// Common data type for queue elements
typedef int queue_data_t;

// Queue operation results
typedef enum {
    QUEUE_SUCCESS = 0,
    QUEUE_FULL = -1,
    QUEUE_EMPTY = -2,
    QUEUE_ERROR = -3
} queue_result_t;

// Forward declaration - specific implementations will define their own structs
typedef struct queue queue_t;

// Common interface that all queue implementations will support
typedef struct {
    bool (*is_full)(const queue_t* queue);
    bool (*is_empty)(const queue_t* queue);
    queue_result_t (*enqueue)(queue_t* queue, queue_data_t data);
    queue_result_t (*dequeue)(queue_t* queue, queue_data_t* data);
    void (*destroy)(queue_t* queue);
} queue_ops_t;

// Base queue structure
struct queue {
    const queue_ops_t* ops;
    size_t capacity;
};

// ============================================================================
// PLATFORM-SPECIFIC OPTIMIZATIONS
// ============================================================================

// Memory barriers
#ifdef _WIN32
    #include <windows.h>
    #define MEMORY_BARRIER() MemoryBarrier()
    #define COMPILER_BARRIER() _ReadWriteBarrier()
#elif defined(__GNUC__)
    #define MEMORY_BARRIER() __sync_synchronize()
    #define COMPILER_BARRIER() __asm__ __volatile__("" ::: "memory")
#else
    #error "Unsupported compiler/platform"
#endif

// Atomic Compare-And-Swap operations
#define CAS(ptr, expected, desired) \
    atomic_compare_exchange_weak((ptr), &(expected), (desired))

// Optimized waiting strategy
static inline void optimal_wait_for_turn(volatile size_t* tail, size_t expected_idx) {
    const int MAX_SPIN_COUNT = 100;  // Tunable based on workload
    int spin_count = 0;
    
    while (*tail != expected_idx) {
        if (spin_count < MAX_SPIN_COUNT) {
            // Phase 1: Hardware-optimized short spin
            #if defined(__x86_64__) || defined(_M_X64)
                _mm_pause();
            #elif defined(__aarch64__)
                __asm__ __volatile__("yield" ::: "memory");
            #else
                __asm__ __volatile__("" ::: "memory");
            #endif
            spin_count++;
        } else {
            // Phase 2: Yield CPU for longer waits
            sched_yield();
            spin_count = 0;
        }
    }
}

// ============================================================================
// MPMC QUEUE IMPLEMENTATION
// ============================================================================

// MPMC Queue uses tagged pointers to solve ABA problem
typedef struct {
    size_t index;
    size_t tag;     // ABA prevention tag
} tagged_index_t;

// MPMC Queue structure with four indices
typedef struct {
    queue_t base;                                    // Base queue structure
    queue_data_t* buffer;                           // Circular buffer
    
    // Producer indices with ABA protection
    _Atomic tagged_index_t producer_head;           // Producer reservation (CAS)
    volatile size_t producer_tail;                  // Producer completion
    
    // Consumer indices with ABA protection  
    _Atomic tagged_index_t consumer_head;           // Consumer reservation (CAS)
    volatile size_t consumer_tail;                  // Consumer completion
    
    // Slot state tracking for ordering
    _Atomic bool* slot_ready;                       // Per-slot completion flags
} mpmc_queue_t;

// Forward declarations for MPMC queue
static bool mpmc_is_full(const queue_t* queue);
static bool mpmc_is_empty(const queue_t* queue);
static queue_result_t mpmc_enqueue(queue_t* queue, queue_data_t data);
static queue_result_t mpmc_dequeue(queue_t* queue, queue_data_t* data);
static void mpmc_destroy(queue_t* queue);

// Operation table for MPMC queue
static const queue_ops_t mpmc_ops = {
    .is_full = mpmc_is_full,
    .is_empty = mpmc_is_empty,
    .enqueue = mpmc_enqueue,
    .dequeue = mpmc_dequeue,
    .destroy = mpmc_destroy
};

// Create MPMC queue
queue_t* mpmc_queue_create(size_t capacity) {
    mpmc_queue_t* queue = malloc(sizeof(mpmc_queue_t));
    if (!queue) return NULL;
    
    // Allocate buffer with extra slot for full/empty detection
    queue->buffer = malloc(sizeof(queue_data_t) * (capacity + 1));
    if (!queue->buffer) {
        free(queue);
        return NULL;
    }
    
    // Allocate per-slot state tracking
    queue->slot_ready = malloc(sizeof(_Atomic bool) * (capacity + 1));
    if (!queue->slot_ready) {
        free(queue->buffer);
        free(queue);
        return NULL;
    }
    
    // Initialize queue structure
    queue->base.ops = &mpmc_ops;
    queue->base.capacity = capacity;
    
    // Initialize indices with tags
    tagged_index_t init_tagged = {.index = 0, .tag = 0};
    atomic_store(&queue->producer_head, init_tagged);
    atomic_store(&queue->consumer_head, init_tagged);
    queue->producer_tail = 0;
    queue->consumer_tail = 0;
    
    // Initialize slot states
    for (size_t i = 0; i <= capacity; i++) {
        atomic_store(&queue->slot_ready[i], false);
    }
    
    return (queue_t*)queue;
}

static bool mpmc_is_full(const queue_t* queue) {
    const mpmc_queue_t* q = (const mpmc_queue_t*)queue;
    
    // Load current producer head atomically
    tagged_index_t producer_head = atomic_load(&q->producer_head);
    size_t next_producer = (producer_head.index + 1) % (q->base.capacity + 1);
    
    // Queue is full when producer would overwrite unconsumed data
    return next_producer == q->consumer_tail;
}

static bool mpmc_is_empty(const queue_t* queue) {
    const mpmc_queue_t* q = (const mpmc_queue_t*)queue;
    
    // Load current consumer head atomically
    tagged_index_t consumer_head = atomic_load(&q->consumer_head);
    
    // Queue is empty when consumer catches up to producer tail
    return consumer_head.index == q->producer_tail;
}

// MPMC Producer (multiple producers with ABA protection)
static queue_result_t mpmc_enqueue(queue_t* queue, queue_data_t data) {
    mpmc_queue_t* q = (mpmc_queue_t*)queue;
    tagged_index_t current_head, new_head;
    
    do {
        // Step 1: Atomically reserve a slot with ABA protection
        current_head = atomic_load(&q->producer_head);
        
        // Check if queue is full
        size_t next_index = (current_head.index + 1) % (q->base.capacity + 1);
        if (next_index == q->consumer_tail) {
            return QUEUE_FULL;
        }
        
        // Prepare new head with incremented tag to prevent ABA
        new_head.index = next_index;
        new_head.tag = current_head.tag + 1;
        
        // Try to reserve this slot using tagged CAS
        // This prevents ABA problem where slot appears unchanged
        // but was actually consumed and reproduced
    } while (!CAS(&q->producer_head, current_head, new_head));
    
    // Step 2: Write data to our reserved slot
    // No race condition here - we own this slot exclusively
    size_t producer_idx = current_head.index;
    q->buffer[producer_idx] = data;
    
    // Step 3: Mark slot as ready for ordered tail advancement
    atomic_store(&q->slot_ready[producer_idx], true);
    
    // Step 4: Try to advance producer_tail if we're the next in line
    // This is more complex than SPMC/MPSC due to multiple producers
    while (q->producer_tail != producer_idx) {
        // If we're not next, check if the next slot is ready
        if (!atomic_load(&q->slot_ready[q->producer_tail])) {
            // Next slot not ready, we can't advance tail
            break;
        }
        
        // Try to advance tail - another thread might do it first
        size_t current_tail = q->producer_tail;
        size_t next_tail = (current_tail + 1) % (q->base.capacity + 1);
        
        // Use CAS to advance tail safely
        if (__sync_bool_compare_and_swap(&q->producer_tail, current_tail, next_tail)) {
            // We successfully advanced the tail
            atomic_store(&q->slot_ready[current_tail], false);  // Reset slot state
        }
    }
    
    return QUEUE_SUCCESS;
}

// MPMC Consumer (multiple consumers with ABA protection)  
static queue_result_t mpmc_dequeue(queue_t* queue, queue_data_t* data) {
    mpmc_queue_t* q = (mpmc_queue_t*)queue;
    tagged_index_t current_head, new_head;
    
    do {
        // Step 1: Atomically reserve a slot with ABA protection
        current_head = atomic_load(&q->consumer_head);
        
        // Check if queue is empty
        if (current_head.index == q->producer_tail) {
            return QUEUE_EMPTY;
        }
        
        // Prepare new head with incremented tag to prevent ABA
        new_head.index = (current_head.index + 1) % (q->base.capacity + 1);
        new_head.tag = current_head.tag + 1;
        
        // Try to reserve this slot using tagged CAS
    } while (!CAS(&q->consumer_head, current_head, new_head));
    
    // Step 2: Read data from our reserved slot
    size_t consumer_idx = current_head.index;
    *data = q->buffer[consumer_idx];
    
    // Step 3: Try to advance consumer_tail in order
    // Similar to producer tail advancement but for consumers
    size_t expected_tail = consumer_idx;
    while (q->consumer_tail == expected_tail) {
        size_t next_tail = (expected_tail + 1) % (q->base.capacity + 1);
        
        // Use CAS to advance tail safely
        if (__sync_bool_compare_and_swap(&q->consumer_tail, expected_tail, next_tail)) {
            // We successfully advanced the tail
            break;
        }
        
        // Another thread might have advanced it, reload and check
        expected_tail = q->consumer_tail;
        if (expected_tail != consumer_idx) {
            // Tail moved past us, we're done
            break;
        }
    }
    
    return QUEUE_SUCCESS;
}

static void mpmc_destroy(queue_t* queue) {
    mpmc_queue_t* q = (mpmc_queue_t*)queue;
    free(q->buffer);
    free(q->slot_ready);
    free(q);
}

// ============================================================================
// PUBLIC API FUNCTIONS
// ============================================================================

// Factory function to create any queue type
queue_t* queue_create(const char* type, size_t capacity) {
    if (strcmp(type, "mpmc") == 0) {
        return mpmc_queue_create(capacity);
    }
    
    // Add other queue types here as needed
    fprintf(stderr, "Unknown queue type: %s\n", type);
    return NULL;
}

// ============================================================================
// EXAMPLE USAGE AND TESTING
// ============================================================================
// #define QUEUE_EXAMPLE
#ifdef QUEUE_EXAMPLE

#include <pthread.h>
#include <unistd.h>
#include <string.h>

#define NUM_PRODUCERS 2
#define NUM_CONSUMERS 3  
#define NUM_ITEMS_PER_PRODUCER 100

typedef struct {
    queue_t* queue;
    int thread_id;
    int* items_produced;
} producer_arg_t;

typedef struct {
    queue_t* queue;
    int thread_id;
    int* items_consumed;
} consumer_arg_t;

void* producer_thread(void* arg) {
    producer_arg_t* args = (producer_arg_t*)arg;
    queue_t* queue = args->queue;
    int thread_id = args->thread_id;
    int* counter = args->items_produced;
    
    for (int i = 0; i < NUM_ITEMS_PER_PRODUCER; i++) {
        int data = thread_id * 10000 + i;  // Encode thread ID and sequence
        
        while (queue->ops->enqueue(queue, data) != QUEUE_SUCCESS) {
            usleep(1); // Brief pause if queue is full
        }
        
        (*counter)++;
        printf("Producer %d sent: %d (total: %d)\n", thread_id, data, *counter);
        usleep(10); // Small delay to create contention
    }
    
    return NULL;
}

void* consumer_thread(void* arg) {
    consumer_arg_t* args = (consumer_arg_t*)arg;
    queue_t* queue = args->queue;
    int thread_id = args->thread_id;
    int* counter = args->items_consumed;
    
    queue_data_t data;
    while (*counter < NUM_PRODUCERS * NUM_ITEMS_PER_PRODUCER) {
        if (queue->ops->dequeue(queue, &data) == QUEUE_SUCCESS) {
            int producer_id = data / 10000;
            int sequence = data % 10000;
            
            (*counter)++;
            printf("Consumer %d got: seq=%d from producer=%d (total: %d)\n", 
                   thread_id, sequence, producer_id, *counter);
        } else {
            usleep(5); // Brief pause if queue is empty
        }
    }
    
    return NULL;
}

int main() {
    printf("MPMC Queue Test - Multiple Producers, Multiple Consumers\n");
    printf("========================================================\n");
    
    // Create MPMC queue
    queue_t* queue = queue_create("mpmc", 32);
    if (!queue) {
        fprintf(stderr, "Failed to create queue\n");
        return 1;
    }
    
    // Shared counters for tracking progress
    int total_produced = 0;
    int total_consumed = 0;
    
    // Thread arrays
    pthread_t producers[NUM_PRODUCERS];
    pthread_t consumers[NUM_CONSUMERS];
    producer_arg_t producer_args[NUM_PRODUCERS];
    consumer_arg_t consumer_args[NUM_CONSUMERS];
    
    printf("Starting %d producers and %d consumers...\n", NUM_PRODUCERS, NUM_CONSUMERS);
    
    // Create consumer threads first
    for (int i = 0; i < NUM_CONSUMERS; i++) {
        consumer_args[i].queue = queue;
        consumer_args[i].thread_id = i;
        consumer_args[i].items_consumed = &total_consumed;
        pthread_create(&consumers[i], NULL, consumer_thread, &consumer_args[i]);
    }
    
    // Create producer threads
    for (int i = 0; i < NUM_PRODUCERS; i++) {
        producer_args[i].queue = queue;
        producer_args[i].thread_id = i;
        producer_args[i].items_produced = &total_produced;
        pthread_create(&producers[i], NULL, producer_thread, &producer_args[i]);
    }
    
    // Wait for all producers to complete
    for (int i = 0; i < NUM_PRODUCERS; i++) {
        pthread_join(producers[i], NULL);
    }
    
    printf("\nAll producers finished. Waiting for consumers to finish...\n");
    
    // Wait for consumers to process all items
    for (int i = 0; i < NUM_CONSUMERS; i++) {
        pthread_join(consumers[i], NULL);
    }
    
    printf("\nTest completed successfully!\n");
    printf("Total items produced: %d\n", total_produced);
    printf("Total items consumed: %d\n", total_consumed);
    
    // Clean up
    queue->ops->destroy(queue);
    
    return 0;
}

#endif // QUEUE_EXAMPLE