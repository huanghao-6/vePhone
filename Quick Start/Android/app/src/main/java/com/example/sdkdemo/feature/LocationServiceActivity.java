package com.example.sdkdemo.feature;

import android.os.Bundle;
import android.util.Log;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.RadioGroup;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.appcompat.widget.LinearLayoutCompat;
import androidx.appcompat.widget.SwitchCompat;

import com.blankj.utilcode.constant.PermissionConstants;
import com.blankj.utilcode.util.PermissionUtils;
import com.example.sdkdemo.R;
import com.example.sdkdemo.base.BasePlayActivity;
import com.example.sdkdemo.util.ScreenUtil;
import com.example.sdkdemo.util.SdkUtil;
import com.volcengine.cloudphone.apiservice.LocationService;
import com.volcengine.phone.PhonePlayConfig;
import com.volcengine.phone.VePhoneEngine;

import java.text.MessageFormat;
import java.util.Map;

/**
 * 该类用于展示与定位服务{@link LocationService}相关的功能接口
 * 使用该服务可以实现向云端实例发送本地设备位置信息的功能。
 */
public class LocationServiceActivity extends BasePlayActivity {

    private FrameLayout mContainer;
    LocationService mLocationService;
    private SwitchCompat mSwShowOrHide, mSwEnableLocationService;
    private LinearLayoutCompat mLlButtons;
    private RadioGroup mRgLocationMode;
    private Button mBtnSetRemoteMockLocation, mBtnGet;


    @Override
    protected void onCreate(@Nullable Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        ScreenUtil.adaptHolePhone(this);
        setContentView(R.layout.activity_location);
        initView();
        initPlayConfigAndStartPlay();
        // 若使用场景涉及到定位功能，可以提前申请好定位权限，也可以在云端触发定位请求时再进行定位授权
        PermissionUtils.permission(PermissionConstants.LOCATION).request();
    }

    private void initView() {
        mContainer = findViewById(R.id.container);
        mSwShowOrHide = findViewById(R.id.sw_show_or_hide);
        mSwEnableLocationService = findViewById(R.id.sw_enable_location_service);
        mLlButtons = findViewById(R.id.ll_buttons);
        mRgLocationMode = findViewById(R.id.rg_mode);
        mBtnSetRemoteMockLocation = findViewById(R.id.btn_set_mock_location);
        mBtnGet = findViewById(R.id.btn_get);

        mSwShowOrHide.setOnCheckedChangeListener((buttonView, isChecked) -> {
            mLlButtons.setVisibility(isChecked ? View.VISIBLE : View.GONE);
        });

        /*
         * enableLocationService(boolean enable) -- 定位服务开关
         */
        mSwEnableLocationService.setOnCheckedChangeListener((v, enable) -> {
            if (mLocationService != null) {
                mLocationService.enableLocationService(enable);
            }
            else {
                Log.e(TAG, "mLocationService == null");
            }
        });

        /*
         * setLocationServiceMode(int mode) -- 设置定位服务模式
         *
         * @param mode 定位服务模式
         *             MODE_AUTO(0) -- 自动模式，当收到远端实例指令时自动获取定位上报并触发回调
         *                              {@link LocationService.LocationEventListener#onSentLocalLocation(LocationService.LocationInfo)}
         *             MODE_MANUAL(1) -- 手动模式，当收到远端实例指令时触发回调
         *                              {@link LocationService.LocationEventListener#onReceivedRemoteLocationRequest(LocationService.RequestOptions)}
         *                              以及{@link LocationService.LocationEventListener#onRemoteLocationRequestEnded()}
         */
        mRgLocationMode.setOnCheckedChangeListener((radioGroup, checkedId) -> {
            if (mLocationService != null) {
                mLocationService.setLocationServiceMode(
                        checkedId == R.id.rb_auto ? LocationService.MODE_AUTO : LocationService.MODE_MANUAL);
            }
            else {
                Log.e(TAG, "mLocationService == null");
            }
        });

        /*
         * setRemoteLocationMock(LocationInfo location)
         * 更新云端实例位置信息
         *
         * @param location 位置信息
         * @return 0 -- 方法调用成功
         *        -1 -- 方法调用失败
         */
        mBtnSetRemoteMockLocation.setOnClickListener(v -> {
            if (mLocationService != null) {
                mLocationService.setRemoteLocationMock(new LocationService.LocationInfo(138.2, 120.3));
            }
            else {
                Log.e(TAG, "mLocationService == null");
            }
        });

        /*
         * isLocationServiceEnabled() -- 是否开启定位服务
         * getLocationServiceMode() -- 获取定位服务模式
         */
        mBtnGet.setOnClickListener(view -> {
            if (mLocationService != null) {
                String mode = mLocationService.getLocationServiceMode() == LocationService.MODE_AUTO ? "auto" : "manual";
                showToast("enable: " + mLocationService.isLocationServiceEnabled() + ", mode: " + mode);
            }
            else {
                Log.e(TAG, "mLocationService == null");
            }
        });

    }

    private void initPlayConfigAndStartPlay() {
        SdkUtil.PlayAuth auth = SdkUtil.getPlayAuth(this);
        SdkUtil.checkPlayAuth(auth,
                p -> {
                    PhonePlayConfig.Builder builder = new PhonePlayConfig.Builder();
                    builder.userId(SdkUtil.getClientUid())
                            .ak(auth.ak)
                            .sk(auth.sk)
                            .token(auth.token)
                            .container(mContainer)
                            .enableLocalKeyboard(true)
                            .enableLocationService(true)
                            .roundId(SdkUtil.getRoundId())
                            .podId(auth.podId)
                            .productId(auth.productId)
                            .streamListener(this);
                    VePhoneEngine.getInstance().start(builder.build(), this);
                },
                p -> {
                    showTipDialog(MessageFormat.format(getString(R.string.invalid_phone_play_config) , p));
                });
    }

    @Override
    protected void onResume() {
        super.onResume();
        VePhoneEngine.getInstance().resume();
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    }

    @Override
    protected void onPause() {
        super.onPause();
        VePhoneEngine.getInstance().pause();
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
    }

    @Override
    public void finish() {
        VePhoneEngine.getInstance().stop();
        super.finish();
    }

    @Override
    public void onServiceInit(@NonNull Map<String, Object> extras) {
        super.onServiceInit(extras);
        mLocationService = VePhoneEngine.getInstance().getLocationService();
        if (mLocationService != null) {
            /**
             * setLocationEventListener(LocationEventListener listener) -- 设置定位事件监听器
             */
            mLocationService.setLocationEventListener(new LocationService.LocationEventListener() {
                /**
                 * 收到远端实例位置请求的回调
                 *
                 * @param options 位置请求选项
                 */
                @Override
                public void onReceivedRemoteLocationRequest(LocationService.RequestOptions options) {
                    Log.i(TAG, "[onReceivedRemoteLocationRequest] options: " + options);
                }

                /**
                 * 远端实例定位请求结束
                 */
                @Override
                public void onRemoteLocationRequestEnded() {
                    Log.i(TAG, "[onRemoteLocationRequestEnded]");
                }

                /**
                 * 在自动定位模式下，向远端实例发送本地设备位置信息后的回调
                 *
                 * @param info 发送到云端实例的本地设备位置信息
                 */
                @Override
                public void onSentLocalLocation(LocationService.LocationInfo info) {
                    Log.i(TAG, "[onSentLocalLocation] info: " + info);
                }

                /**
                 * 远端实例位置更新后的回调
                 * 当手动调用{@link LocationService#setRemoteLocationMock(LocationService.LocationInfo)}时触发该回调；
                 * 当设置为自动获取或者没有调用{@link LocationService#setRemoteLocationMock(LocationService.LocationInfo)}的时候不会触发。
                 *
                 * @param info 远端实例更新的位置信息
                 */
                @Override
                public void onRemoteLocationUpdated(LocationService.LocationInfo info) {
                    Log.i(TAG, "[onRemoteLocationUpdated] info: " + info);
                }
            });
        }
        else {
            Log.e(TAG, "mLocationService == null");
        }
    }

    @Override
    public void onWarning(int code, String msg) {
        super.onWarning(code, msg);
        switch (code) {
            case 30007:  //WARNING_SDK_LACK_OF_LOCATION_PERMISSION
                showTipDialog("云端发起定位请求，但客户端无定位权限，是否申请系统定位权限？",
                        (dialog, which) -> {
                            // 请求定位权限，SDK内部仅检查权限不会主动申请任何运行时权限
                            PermissionUtils.permission(PermissionConstants.LOCATION).request();
                        });
                break;
            case 30013:  //WARNING_SDK_LOCATION_DISABLED
                LocationService service = mLocationService;
                if (service != null) {
                    showTipDialog("收到云端请求定位，但客户端未开启定位上报功能，是否开启定位上报功能？",
                            (dialog, which) -> {
                                // 根据业务需求决定是否开启定位权限，若不需要则忽略此告警码；若需要则调用下面接口动态开启定位功能
                                service.enableLocationService(true);
                            });
                }
                break;
            default:
                break;
        }
    }
}
