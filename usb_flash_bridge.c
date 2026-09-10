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

typedef void (*progress_callback_t)(int current, int total);

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

// Write 4096-byte blocks to Pipe 1 (Endpoint 0x06 OUT)
int leobog_flash_blocks(const uint8_t *data, int total_blocks, progress_callback_t cb) {
    if (!data || total_blocks <= 0) return -10;

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

    IOReturn kr = (*intf)->USBInterfaceOpen(intf);
    if (kr != kIOReturnSuccess) {
        (*intf)->Release(intf);
        return -4;
    }

    int ret = 0;
    for (int b = 0; b < total_blocks; b++) {
        const uint8_t *block_ptr = data + (b * FLASH_BLOCK_SIZE);

        // Write 4096 bytes to Pipe 1 with 2000ms timeout
        kr = (*intf)->WritePipeTO(intf, 1, (void*)block_ptr, FLASH_BLOCK_SIZE, 2000, 2000);
        if (kr != kIOReturnSuccess) {
            // If WritePipeTO is not supported on this pipe type, try WritePipe
            kr = (*intf)->WritePipe(intf, 1, (void*)block_ptr, FLASH_BLOCK_SIZE);
        }

        if (kr != kIOReturnSuccess) {
            fprintf(stderr, "WritePipe failed at block %d/%d with error 0x%08x\n", b, total_blocks, kr);
            ret = -5;
            break;
        }

        if (b == 0) {
            usleep(500000); // 500ms for flash sector erase
        } else {
            usleep(15000);  // 15ms
        }

        if (cb) {
            cb(b + 1, total_blocks);
        }
    }

    (*intf)->USBInterfaceClose(intf);
    (*intf)->Release(intf);
    return ret;
}
