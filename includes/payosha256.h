#pragma once

#include <string>
#include <iostream>

#include "happyhttp.h"
#include "../lifelib/soup/sha256.h"

class ProcessedResponse {
public:
    int m_Status;           // Status-Code
    std::string m_Reason;   // Reason-Phrase
    int length;             // String length (in bytes)
    bool completed;         // Indicates whether successful
    std::stringstream contents;

    ProcessedResponse() {
        length = 0;
        m_Status = 0;
        completed = false;
    }
};

int __catagolue_retries = 0;
const char* __possible_catagolues[] = {"catagolue.hatsya.com", "catagolue.appspot.com", "gol.hatsya.co.uk"};
#define CATAGOLUE_NAME __possible_catagolues[__catagolue_retries % 3]
#define INCREMENT_CATAGOLUE __catagolue_retries += 1

void OnBegin( const happyhttp::Response* r, void* userdata )
{
    ProcessedResponse* presp = static_cast<ProcessedResponse*>(userdata);

    presp->m_Status = r->getstatus();
    presp->m_Reason = r->getreason();
    presp->length = 0;
}

void OnData( const happyhttp::Response* r, void* userdata, const unsigned char* data, int n )
{
    ProcessedResponse* presp = static_cast<ProcessedResponse*>(userdata);
    for (int i = 0; i < n; i++)
        presp->contents << data[i];
    presp->length += n;
    (void) (r);
}

void OnComplete( const happyhttp::Response* r, void* userdata )
{
    ProcessedResponse* presp = static_cast<ProcessedResponse*>(userdata);
    presp->completed = true;
    // std::cout << "Response completed (" << presp->length << " bytes): " << presp->m_Status << " " << presp->m_Reason << std::endl;
    (void) (r);
}

void increment_catagolue() {

        std::string oldcat = CATAGOLUE_NAME;
        INCREMENT_CATAGOLUE;
        std::string newcat = CATAGOLUE_NAME;
        std::cerr << "henceforth trying " << newcat;
        std::cerr << " instead of " << oldcat << "..." << std::endl;

}

#ifdef USE_CURL
#include <curl/curl.h>

static size_t curl_write_string(void *contents, size_t size, size_t nmemb, void *userp)
{
    ((std::string*)userp)->append((char*)contents, size * nmemb);
    return size * nmemb;
}

std::string catagolueRequest(const char *payload, const char *endpoint)
{
    CURL *curl = curl_easy_init();
    if (!curl) {
        std::cerr << "curl_easy_init() failed; ";
        increment_catagolue();
        return "";
    }

    std::string url = "https://" + std::string(CATAGOLUE_NAME) + std::string(endpoint);
    std::string response_data;

    struct curl_slist *headers = NULL;
    headers = curl_slist_append(headers, "Connection: close");
    headers = curl_slist_append(headers, "Content-Type: text/plain");
    headers = curl_slist_append(headers, "User-Agent: Anaconda-urllib/2.7");

    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, payload);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, curl_write_string);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response_data);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 30L);
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);

    CURLcode res = curl_easy_perform(curl);
    long http_status = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_status);

    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK) {
        std::cerr << "Internet does not exist (" << curl_easy_strerror(res) << "); ";
        increment_catagolue();
        return "";
    }

    if (http_status == 200) {
        return response_data;
    } else {
        std::cerr << "Bad status: " << http_status << std::endl;
        return "";
    }
}
#else
std::string catagolueRequest(const char *payload, const char *endpoint)
{

    const char* headers[] =
    {
        "Connection", "close",
        "Content-Type", "text/plain",
        "User-Agent", "Anaconda-urllib/2.7",
        0
    };

    try {

    // std::cout << "Making connection..." << std::endl;
    happyhttp::Connection conn( CATAGOLUE_NAME , 80 );
    conn.connect();
    // std::cout << "...connection made." << std::endl;
    ProcessedResponse processedResp; // create an empty ProcessedResponse object
    ProcessedResponse* presp = &processedResp; // and obtain a pointer to it
    conn.setcallbacks( OnBegin, OnData, OnComplete, (void*) presp);
    // std::cout << "Sending request..." << std::endl;
    conn.request( "POST", endpoint, headers, (const unsigned char*)payload, strlen(payload) );
    // std::cout << "...request sent." << std::endl;

    while( conn.outstanding() )
        conn.pump();

    if (presp->completed == false) {
        std::cerr << "Response incomplete." << std::endl;
        return "";
    }

    if (presp->m_Status == 200) {
        std::string response = presp->contents.str();
        return response;
    } else {
        std::cerr << "Bad status: " << presp->m_Status << std::endl;
        return "";
    }

    }
    catch( happyhttp::Wobbly& e )
    {
        std::cerr << "Internet does not exist; ";
        increment_catagolue();
        return "";
    }

}
#endif


std::string authenticate(const char *payosha256_key, const char *operation_name)
{
    // std::cout << "Authenticating with Catagolue via the payosha256 protocol..." << std::endl;

    std::string payload = "payosha256:get_token:";
    payload += payosha256_key;
    payload += ":";
    payload += operation_name;

    std::string resp = catagolueRequest(payload.c_str(), "/payosha256");

    if (resp.length() == 0) {
        std::cout << "No response!" << std::endl;
        return "";
    }

    std::stringstream ss(resp);
    std::string item;
    std::string target;
    std::string token;

    while (std::getline(ss, item, '\n')) {
        std::stringstream ss2(item);
        std::string item2;

        if (std::getline(ss2, item2, ':')) {
            if (std::getline(ss2, item2, ':')) {
                if (item2 == "good") {
                    if (std::getline(ss2, target, ':')) {
                        std::getline(ss2, token, ':');
                    }
                }
            }
        }

        if (token.length() > 0)
            break;
    }

    if (token.length() == 0) {
        std::cerr << "Invalid response from payosha256; ";
        increment_catagolue();
        return "";
    } else {
        // std::cout << "Token " << token << " obtained from payosha256." << std::endl;
        // std::cout << "Performing proof of work with target " << target << "..." << std::endl;

        for (int nonce = 0; nonce < 244823040; nonce++) {

            std::string prehash = strConcat(token, ':', nonce);
            std::string posthash = sha256(prehash);

            if (posthash < target) {
                // std::cout << "...finished proof of work after " << nonce << " iterations!" << std::endl;

                return "payosha256:pay_token:"+prehash+"\n";
            }
        }

        // std::cout << "...work interrupted due to lethargy." << std::endl;

        return "";
    }
}

