
using UnityEngine;
using UnityEngine.InputSystem;

public class CameraController : MonoBehaviour
{
    [Header("Movement")]
    public float moveSpeed      = 20f;
    public float fastMultiplier = 3f;
    public float smoothing      = 8f;

    [Header("Look")]
    public float mouseSensitivity = 2f;
    public float minY             = -80f;
    public float maxY             = 80f;

    [Header("Clipping")]
    public float minHeight = 0.5f;

    private Vector3 currentVelocity;
    private float   rotX = 0f;
    private float   rotY = 0f;
    private bool    cursorLocked = false;

    void Start()
    {
        rotX = transform.eulerAngles.y;
        rotY = transform.eulerAngles.x;
    }

    void Update()
    {
        HandleCursorLock();
        if (cursorLocked)
        {
            HandleLook();
            HandleMovement();
        }
        ClampHeight();
    }

    void HandleCursorLock()
    {
        if (Mouse.current.rightButton.wasPressedThisFrame)
        {
            cursorLocked     = true;
            Cursor.lockState = CursorLockMode.Locked;
            Cursor.visible   = false;
        }

        if (Keyboard.current.escapeKey.wasPressedThisFrame)
        {
            cursorLocked     = false;
            Cursor.lockState = CursorLockMode.None;
            Cursor.visible   = true;
        }
    }

    void HandleLook()
    {
        Vector2 mouseDelta = Mouse.current.delta.ReadValue();
        rotX += mouseDelta.x * mouseSensitivity * Time.deltaTime * 10f;
        rotY -= mouseDelta.y * mouseSensitivity * Time.deltaTime * 10f;
        rotY  = Mathf.Clamp(rotY, minY, maxY);
        transform.rotation = Quaternion.Euler(rotY, rotX, 0f);
    }

    void HandleMovement()
    {
        bool fast = Keyboard.current.leftShiftKey.isPressed;
        float speed = fast ? moveSpeed * fastMultiplier : moveSpeed;

        Vector3 input = Vector3.zero;

        if (Keyboard.current.wKey.isPressed) input.z =  1f;
        if (Keyboard.current.sKey.isPressed) input.z = -1f;
        if (Keyboard.current.aKey.isPressed) input.x = -1f;
        if (Keyboard.current.dKey.isPressed) input.x =  1f;
        if (Keyboard.current.eKey.isPressed) input.y =  1f;
        if (Keyboard.current.qKey.isPressed) input.y = -1f;

        Vector3 targetVelocity = transform.TransformDirection(input.normalized) * speed;
        currentVelocity = Vector3.Lerp(
            currentVelocity,
            targetVelocity,
            Time.deltaTime * smoothing
        );

        transform.position += currentVelocity * Time.deltaTime;
    }

    void ClampHeight()
    {
        if (transform.position.y < minHeight)
        {
            transform.position = new Vector3(
                transform.position.x,
                minHeight,
                transform.position.z
            );
        }
    }
}