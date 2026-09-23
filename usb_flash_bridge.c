#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <IOKit/IOCFPlugIn.h>
#include <IOKit/usb/IOUSBLib.h>

#define LEOBOG_VID 0x0C45
#define LEOBOG_PID 0x800A
#define FLASH_INTERFACE_NUM 3
#define FLASH_BLOCK_SIZE 4096

static io_service_t find_interface3_service() {
    CFMutableDictionaryRef matchingDict = IOServiceMatching(kIOUSBInterfaceClassName);
    if (!matchingDict) return IO_OBJECT_NULL;

    io_iterator_t iter;
    if (IOServiceGetMatchingServices(kIOMainPortDefault, matchingDict, &iter) != KERN_SUCCESS) {
        return IO_OBJECT_NULL;
    }

    io_service_t intfService;
    io_service_t found = IO_OBJECT_NULL;

    while ((intfService = IOIteratorNext(iter))) {
        CFMutableDictionaryRef props = NULL;
        if (IORegistryEntryCreateCFProperties(intfService, &props, kCFAllocatorDefault, 0) == KERN_SUCCESS && props) {
            CFTypeRef tVid = CFDictionaryGetValue(props, CFSTR("idVendor"));
            CFTypeRef tPid = CFDictionaryGetValue(props, CFSTR("idProduct"));
            CFTypeRef tNum = CFDictionaryGetValue(props, CFSTR("bInterfaceNumber"));

            int vid = 0, pid = 0, num = -1;
            if (tVid) CFNumberGetValue((CFNumberRef)tVid, kCFNumberIntType, &vid);
            if (tPid) CFNumberGetValue((CFNumberRef)tPid, kCFNumberIntType, &pid);
            if (tNum) CFNumberGetValue((CFNumberRef)tNum, kCFNumberIntType, &num);

            if (vid == LEOBOG_VID && pid == LEOBOG_PID && num == FLASH_INTERFACE_NUM) {
                found = intfService;
                CFRelease(props);
                break;
            }
            CFRelease(props);
        }
        IOObjectRelease(intfService);
    }
    IOObjectRelease(iter);
    return found;
}

// Test opening interface 3
int leobog_test_interface3() {
    io_service_t service = find_interface3_service();
    if (service == IO_OBJECT_NULL) {
        return -1; // Not found
    }

    IOCFPlugInInterface **plugInInterface = NULL;
    SInt32 score;
    HRESULT res = IOCreatePlugInInterfaceForService(service,
                                                    kIOUSBInterfaceUserClientTypeID,
                                                    kIOCFPlugInInterfaceID,
                                                    &plugInInterface,
                                                    &score);
    IOObjectRelease(service);
    if (res != S_OK || !plugInInterface) {
        return -2; // Plugin error
    }

    IOUSBInterfaceInterface **intf = NULL;
    (*plugInInterface)->QueryInterface(plugInInterface,
                                       CFUUIDGetUUIDBytes(kIOUSBInterfaceInterfaceID),
                                       (LPVOID*)&intf);
    (*plugInInterface)->Release(plugInInterface);
    if (!intf) {
        return -3; // QueryInterface error
    }

    IOReturn kr = (*intf)->USBInterfaceOpen(intf);
    if (kr != kIOReturnSuccess) {
        (*intf)->Release(intf);
        return -4; // Open error
    }

    (*intf)->USBInterfaceClose(intf);
    (*intf)->Release(intf);
    return 0; // Success
}

// Per-block session API: the caller must wait for the interface-2 ack between blocks.
static IOUSBInterfaceInterface **g_intf = NULL;

int leobog_flash_open(void) {
    if (g_intf) return 0;

    io_service_t service = find_interface3_service();
    if (service == IO_OBJECT_NULL) {
        return -1;
    }

    IOCFPlugInInterface **plugInInterface = NULL;
    SInt32 score;
    HRESULT res = IOCreatePlugInInterfaceForService(service,
                                                    kIOUSBInterfaceUserClientTypeID,
                                                    kIOCFPlugInInterfaceID,
                                                    &plugInInterface,
                                                    &score);
    IOObjectRelease(service);
    if (res != S_OK || !plugInInterface) {
        return -2;
    }

    IOUSBInterfaceInterface **intf = NULL;
    (*plugInInterface)->QueryInterface(plugInInterface,
                                       CFUUIDGetUUIDBytes(kIOUSBInterfaceInterfaceID),
                                       (LPVOID*)&intf);
    (*plugInInterface)->Release(plugInInterface);
    if (!intf) {
        return -3;
    }

    if ((*intf)->USBInterfaceOpen(intf) != kIOReturnSuccess) {
        (*intf)->Release(intf);
        return -4;
    }

    g_intf = intf;
    return 0;
}

// Write one 4096-byte block to Pipe 1 (EP 0x06 interrupt OUT)
int leobog_flash_write_block(const uint8_t *block) {
    if (!g_intf) return -1;
    if (!block) return -10;

    IOReturn kr = (*g_intf)->WritePipeTO(g_intf, 1, (void*)block, FLASH_BLOCK_SIZE, 2000, 2000);
    // Untimed WritePipe only when the timed call is unsupported; after a timeout it would block forever
    if (kr == kIOReturnUnsupported || kr == kIOReturnBadArgument) {
        kr = (*g_intf)->WritePipe(g_intf, 1, (void*)block, FLASH_BLOCK_SIZE);
    } else if (kr != kIOReturnSuccess) {
        (*g_intf)->ClearPipeStallBothEnds(g_intf, 1);
    }
    if (kr != kIOReturnSuccess) {
        fprintf(stderr, "WritePipe failed with error 0x%08x\n", kr);
        return -5;
    }
    return 0;
}

void leobog_flash_close(void) {
    if (!g_intf) return;
    (*g_intf)->USBInterfaceClose(g_intf);
    (*g_intf)->Release(g_intf);
    g_intf = NULL;
}
