package app.dsh.mobile.engine

import org.junit.Test

/** Copy with LogPolicyJvmTest into the app's src/test tree when JUnit4 is available. */
class LogPolicyTest {
    @Test fun bearer() = LogPolicyJvmTest.runCase("bearer")
    @Test fun apiKeyHeaders() = LogPolicyJvmTest.runCase("api_key_headers")
    @Test fun jsonFields() = LogPolicyJvmTest.runCase("json_fields")
    @Test fun authorizationHeader() = LogPolicyJvmTest.runCase("authorization_header")
    @Test fun urlTokens() = LogPolicyJvmTest.runCase("url_tokens")
    @Test fun tokenFields() = LogPolicyJvmTest.runCase("token_fields")
    @Test fun skKeys() = LogPolicyJvmTest.runCase("sk_keys")
    @Test fun ordinaryText() = LogPolicyJvmTest.runCase("ordinary_text")
    @Test fun veryLongLine() = LogPolicyJvmTest.runCase("very_long_line")
    @Test fun cjkEmojiByteLimit() = LogPolicyJvmTest.runCase("cjk_emoji_byte_limit")
    @Test fun utf8BoundaryMatrix() = LogPolicyJvmTest.runCase("utf8_boundary_matrix")
    @Test fun exactFit() = LogPolicyJvmTest.runCase("exact_fit")
    @Test fun scanBoundarySurrogate() = LogPolicyJvmTest.runCase("scan_boundary_surrogate")
    @Test fun invalidSurrogatesControls() = LogPolicyJvmTest.runCase("invalid_surrogates_controls")
    @Test fun hugeVirtualInput() = LogPolicyJvmTest.runCase("huge_virtual_input")
    @Test fun hugeVirtualSecret() = LogPolicyJvmTest.runCase("huge_virtual_secret")
    @Test fun totalBufferBytes() = LogPolicyJvmTest.runCase("total_buffer_bytes")
    @Test fun emptyEntryCountLimit() = LogPolicyJvmTest.runCase("empty_entry_count_limit")
    @Test fun concurrentWritersSnapshots() = LogPolicyJvmTest.runCase("concurrent_writers_snapshots")
    @Test fun deterministicOutput() = LogPolicyJvmTest.runCase("deterministic_output")
    @Test fun clearDetachedSnapshot() = LogPolicyJvmTest.runCase("clear_detached_snapshot")
    @Test fun illegalParameters() = LogPolicyJvmTest.runCase("illegal_parameters")
    @Test fun safeErrorChannel() = LogPolicyJvmTest.runCase("safe_error_channel")
    @Test fun errorDoesNotReadThrowable() = LogPolicyJvmTest.runCase("error_does_not_read_throwable")
    @Test fun quotedSecretEscaping() = LogPolicyJvmTest.runCase("quoted_secret_escaping")
    @Test fun environmentContainers() = LogPolicyJvmTest.runCase("environment_containers")
    @Test fun deepMalformedContainer() = LogPolicyJvmTest.runCase("deep_malformed_container")
    @Test fun cookieHeader() = LogPolicyJvmTest.runCase("cookie_header")
    @Test fun quotedBearer() = LogPolicyJvmTest.runCase("quoted_bearer")
    @Test fun bearerInTokenField() = LogPolicyJvmTest.runCase("bearer_in_token_field")
}
