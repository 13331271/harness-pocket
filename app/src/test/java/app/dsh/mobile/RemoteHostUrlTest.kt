package app.dsh.mobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class RemoteHostUrlTest {

    @Test
    fun addsHttpSchemeWhenMissing() {
        assertEquals("http://192.168.1.10:3080", RemoteHostUrl.normalize("192.168.1.10:3080"))
    }

    @Test
    fun keepsHttpsScheme() {
        assertEquals("https://dsh.example.com", RemoteHostUrl.normalize(" https://dsh.example.com "))
    }

    @Test
    fun keepsHttpScheme() {
        assertEquals("http://127.0.0.1:3080", RemoteHostUrl.normalize("http://127.0.0.1:3080"))
    }

    @Test
    fun rejectsBlankInput() {
        assertNull(RemoteHostUrl.normalize(""))
        assertNull(RemoteHostUrl.normalize("   "))
    }

    @Test
    fun rejectsEmbeddedWhitespace() {
        assertNull(RemoteHostUrl.normalize("http://host:3080/a b"))
        assertNull(RemoteHostUrl.normalize("host\nname"))
    }

    @Test
    fun rejectsSchemeOnly() {
        assertNull(RemoteHostUrl.normalize("http://"))
    }

    @Test
    fun appendsTokenWithQuestionMark() {
        assertEquals(
            "http://host:3080?token=abc",
            RemoteHostUrl.withToken("http://host:3080", " abc "),
        )
    }

    @Test
    fun appendsTokenWithAmpersandWhenQueryExists() {
        assertEquals(
            "http://host:3080/?x=1&token=abc",
            RemoteHostUrl.withToken("http://host:3080/?x=1", "abc"),
        )
    }

    @Test
    fun ignoresBlankToken() {
        assertEquals("http://host:3080", RemoteHostUrl.withToken("http://host:3080", "   "))
    }

    @Test
    fun buildComposesNormaliseAndToken() {
        assertEquals(
            "http://10.0.0.5:3080?token=t0k",
            RemoteHostUrl.build("10.0.0.5:3080", "t0k"),
        )
        assertNull(RemoteHostUrl.build("  ", "t0k"))
    }

    @Test
    fun originStripsPathQueryAndCredentialsFree() {
        assertEquals("host:3080", RemoteHostUrl.origin("http://host:3080/path?token=abc"))
        assertEquals("host", RemoteHostUrl.origin("https://host/"))
    }
}
