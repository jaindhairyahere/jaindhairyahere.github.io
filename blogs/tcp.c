#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// --- Winsock (Windows) Headers ---
#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
    #pragma comment(lib, "ws2_32.lib") // A linker directive often used on Windows
    #define PORT 8080
    
    // Define cross-platform data types and functions
    typedef SOCKET Socket_FD;
    #define CLOSE_SOCKET(s) closesocket(s)
    #define WSA_STARTUP_SUCCESS 0
    #define SOCKET_ERROR_VAL SOCKET_ERROR // On Windows, error is SOCKET_ERROR
#else
    // --- Linux/Unix Headers (for later) ---
    #include <unistd.h>
    #include <sys/types.h>
    #include <sys/socket.h>
    #include <netinet/in.h>
    #include <arpa/inet.h>
    #define PORT 8080
    
    // Define cross-platform data types and functions
    typedef int Socket_FD;
    #define CLOSE_SOCKET(s) close(s)
    #define WSA_STARTUP_SUCCESS 1 // Not used on Linux, placeholder for flow control
    #define SOCKET_ERROR_VAL -1 // On Linux, error is -1
#endif

// A simple utility function for error handling
void error_exit(const char *msg) {
    perror(msg);
    #ifdef _WIN32
        fprintf(stderr, "Winsock Error Code: %d\n", WSAGetLastError());
        WSACleanup();
    #endif
    exit(EXIT_FAILURE);
}
#define BUFFER_SIZE 4096 

// =======================================================
// Your Task 1: Main Server Logic - Boilerplate & Setup
// =======================================================
int main() {
    // 1. Declare variables
    Socket_FD listen_sock; // The listening socket
    Socket_FD new_sock;    // The new socket for communication with the client
    struct sockaddr_in server_addr, client_addr;
    int addrlen;
    
    // --- Step 1A: Windows-Specific Initialization (WSAStartup) ---
    // Pointers:
    //  - Declare a WSADATA structure.
    //  - Call WSAStartup(MAKEWORD(2, 2), &wsaData)
    //  - Check if the return value is 0 (WSA_STARTUP_SUCCESS). Use error_exit on failure.

    // YOUR IMPLEMENTATION HERE (WSAStartup)
#ifdef _WIN32
    WSADATA wsaData;
    if (WSAStartup(MAKEWORD(2, 2), &wsaData) != WSA_STARTUP_SUCCESS) {
        error_exit("WSAStartup failed");
    }
#endif
    
    // --- Step 2: Create a Socket ---
    // Pointers:
    //  - Call socket(AF_INET, SOCK_STREAM, 0).
    //  - Assign the result to listen_sock.
    //  - Check if the result is SOCKET_ERROR_VAL. Use error_exit on failure.
    
    // YOUR IMPLEMENTATION HERE (socket)
    listen_sock = socket(AF_INET, SOCK_STREAM, 0 /* TCP */);
    if (listen_sock == SOCKET_ERROR_VAL) {
        error_exit("Socket creation failed");
    }

    // --- Step 3: Prepare the Server Address Structure ---
    // Pointers:
    //  - Use bzero or memset to clear server_addr.
    //  - Set server_addr.sin_family to AF_INET.
    //  - Set server_addr.sin_addr.s_addr to htonl(INADDR_ANY) (or inet_addr("127.0.0.1") for local only).
    //  - Set server_addr.sin_port to htons(PORT).
    
    // YOUR IMPLEMENTATION HERE (server_addr setup)
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = htonl(INADDR_ANY);
    server_addr.sin_port = htons(PORT);
    
    // --- Step 4: Bind the Socket to the Address ---
    // Pointers:
    //  - Call bind(listen_sock, (struct sockaddr *)&server_addr, sizeof(server_addr)).
    //  - Check for SOCKET_ERROR_VAL. Use error_exit on failure.
    
    // YOUR IMPLEMENTATION HERE (bind)
    if (bind(listen_sock, (struct sockaddr *)&server_addr, sizeof(server_addr)) == SOCKET_ERROR_VAL) {
        error_exit("Bind failed");
    }

    // --- Step 5: Start Listening for Connections ---
    // Pointers:
    //  - Call listen(listen_sock, 5). (5 is the backlog size).
    //  - Check for SOCKET_ERROR_VAL. Use error_exit on failure.
    
    // YOUR IMPLEMENTATION HERE (listen)
    if (listen(listen_sock, 5) == SOCKET_ERROR_VAL) {
        error_exit("Listen failed");
    }
    
    
    printf("Server listening on port %d...\n", PORT);
    
    // =======================================================
    // Your Task 2: Accept Connection and Communicate
    // =======================================================
    // 1. Accept Connection (Blocks until a client connects)
    // 2. Send Data
    // 3. Close Client Socket

    // YOUR IMPLEMENTATION HERE (Accept, Send, and Close Client)
    
    addrlen = sizeof(client_addr);
    new_sock = accept(listen_sock, (struct sockaddr*) &client_addr, &addrlen);
    if (new_sock == SOCKET_ERROR_VAL){
        error_exit("Accept failed");
    }

    // Convert client IP address to a readable string for logging
    #ifdef _WIN32
        // Winsock uses the 'struct in_addr' directly
        char* client_ip = inet_ntoa(client_addr.sin_addr);
    #else
        // For Linux, inet_ntoa works similarly but ensure headers are right
        // If using modern IPv6-compatible code, use inet_ntop
        char* client_ip = inet_ntoa(client_addr.sin_addr);
    #endif
    
    printf("Successful Connection accepted from IP: %s, Port: %d\n", 
           client_ip, 
           ntohs(client_addr.sin_port)); // Convert port back to host byte order for display


    char* message = "Hello from TCP Server";
    int messageLen = strlen(message);
    if(send(new_sock, message, messageLen, 0) < messageLen){
        error_exit("Send failed or partial message sent");
    }

    // --- 5. Receive Data ---
    // Pointers: Use recv(client_sock, buffer, BUFFER_SIZE - 1, 0)
    int buffer[BUFFER_SIZE];
    int bytes_received = recv(new_sock, buffer, BUFFER_SIZE, -1);
    
    
    // Print the received message if successful
    if (bytes_received > 0) {
        buffer[bytes_received] = '\0'; // Null-terminate the string
        printf("Server message: %s\n", buffer);
    } else if (bytes_received == 0) {
        printf("Connection closed by server.\n");
    } else {
        error_exit("Receive failed");
    }

    // --- 6. Cleanup ---
    // YOUR IMPLEMENTATION HERE (Close and WSACleanup)
    CLOSE_SOCKET(new_sock);
    
    // --- Cleanup (Placeholder for now) ---
    // For now, just close the listening socket and call WSACleanup.
    CLOSE_SOCKET(listen_sock);
    #ifdef _WIN32
        WSACleanup();
    #endif

    return 0;
}